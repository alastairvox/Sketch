import sketchShared
from sketchShared import debug, info, warn, error, critical
import asyncio, aiohttp, aiohttp.web, logging, aiohttp_jinja2, jinja2, aiohttp_session, aiohttp_session.cookie_storage, aiohttp_csrf, secrets, uuid, datetime, pytz, base64, json
from secrets import compare_digest
from urllib.parse import urlencode
from typing import Optional
import sketchAuth, sketchYoutube, sketchDiscord, sketchTwitch
from sketchModels import *

# MARK: SETUP ------------------------------------------------------------------------------------------------------------

# have to override these to fix server error when not providing a header or a form body
class SketchFormPolicy:
    def __init__(self, field_name: str):
        self.field_name = field_name

    async def check(self, request: aiohttp.web.Request, original_value: str) -> bool:
        get = request.match_info.get(self.field_name, None)
        post_req = await request.post() if get is None else None
        post = post_req.get(self.field_name) if post_req is not None else None
        post = post if post is not None else ""
        token = get if get is not None else post
        if not isinstance(token, str) or token=='':
            logging.debug("CSRF failure: Missing token on request form")
            return False
        
        if not original_value:
            logging.debug("CSRF failure: No original value comapring request form fields")
            return False
        
        return compare_digest(token, original_value)

class SketchHeaderPolicy:
    def __init__(self, header_name: str):
        self.header_name = header_name

    async def check(self, request: aiohttp.web.Request, original_value: str) -> bool:
        token = request.headers.get(self.header_name)
        if not isinstance(token, str) or token=='':
            logging.debug("CSRF failure: Missing token on request headers")
            return False
        
        if not original_value:
            logging.debug("CSRF failure: No original value comparing request headers")
            return False
        
        return compare_digest(token, original_value)

class SketchFormAndHeaderPolicy(SketchHeaderPolicy, SketchFormPolicy):
    def __init__(self, header_name: str, field_name: str):
        self.header_name = header_name
        self.field_name = field_name

    async def check(self, request: aiohttp.web.Request, original_value: str) -> bool:
        header_check = await SketchHeaderPolicy.check(self, request, original_value)

        if header_check:
            return True

        form_check = await SketchFormPolicy.check(self, request, original_value)

        if form_check:
            return True

        return False

async def summon():
    info('Summoning...')
    if sketchShared.dev:
        aiohttp_jinja2.setup(app, enable_async=True, loader=jinja2.FileSystemLoader('src/templates'))
    else:
        aiohttp_jinja2.setup(app, enable_async=True, loader=jinja2.FileSystemLoader('templates'))
    
    global clientSession
    clientSession = aiohttp.ClientSession()
    
    app.add_routes(routes)
    subappDiscord.add_routes(subroutesDiscord)
    subappVoice.add_routes(subroutesVoice)
    app.add_domain('discord.drawn.actor', subappDiscord)
    app.add_domain('discord.alastairvox.com', subappDiscord)
    app.add_domain('voice.alastairvox.com', subappVoice)
    
    if sketchShared.dev:
        app.router.add_static('/static/', path='src/static', name='static')
    else:
        app.router.add_static('/static/', path='static', name='static')

    loop = asyncio.get_event_loop()
    await sketchTwitch.bot.wait_until_ready()
    await sketchDiscord.bot.wait_until_ready()
    #  uses internal _run_app since we are managing our own loops
    loop.create_task(aiohttp.web._run_app(app, port=sketchAuth.internalPort, print=None))

async def on_startup(app):
    info('Connected to HTTP server on port ' + sketchAuth.internalPort + '.')

    # TODO disable/remove this for "production"
    logging.getLogger("aiohttp.access").setLevel(logging.WARN)

    # await test('')

async def on_shutdown(app):
    info('Disconnected from HTTP server on port ' + sketchAuth.internalPort + '.')

routes = aiohttp.web.RouteTableDef()
subroutesDiscord = aiohttp.web.RouteTableDef()
subroutesVoice = aiohttp.web.RouteTableDef()
app = aiohttp.web.Application()
subappDiscord = aiohttp.web.Application()
subappVoice = aiohttp.web.Application()

csrf_policy = SketchFormAndHeaderPolicy(field_name='_csrf_token', header_name='Csrf-Token')
csrf_storage = aiohttp_csrf.storage.SessionStorage('csrf_token', secret_phrase=sketchAuth.serverSecret)
aiohttp_csrf.setup(app, policy=csrf_policy, storage=csrf_storage)
aiohttp_session.setup(app, aiohttp_session.cookie_storage.EncryptedCookieStorage(sketchAuth.serverURLSafeSecret, max_age=604800, httponly=True, secure=True, samesite='Lax'))
app.middlewares.append(aiohttp_csrf.csrf_middleware)

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)
global clientSession


# MARK: FUNCTIONS ---------------------------------------------------------------------------------------------------------

async def getSession(request: aiohttp.web.Request) -> aiohttp_session.Session:
    session = await aiohttp_session.get_session(request)
    if session.new:
        info("New session detected, creating UUID for session id...")
        newUUID = str(uuid.uuid4())
        session.set_new_identity(newUUID)
        session['sessionID'] = str(newUUID)
        session['messages'] = []
    return session

async def newSession(request: aiohttp.web.Request) -> aiohttp_session.Session:
    session = await aiohttp_session.new_session(request)
    info("Creating new session, creating UUID for session id...")
    newUUID = str(uuid.uuid4())
    session.set_new_identity(newUUID)
    session['sessionID'] = str(newUUID)
    session['messages'] = []
    return session
    
async def getMessages(session: aiohttp_session.Session) -> list[str]:
    if 'messages' in session and session['messages']:
        messages = session['messages']
        session['messages'] = []
    else:
        messages = []
        
    return messages

# gets discord user object from discord API using access token
async def getDiscordUser(accessToken):
    debug(f'Getting ID from access token: {accessToken}')
    baseURL = 'https://discord.com/api/users/@me'
    headers = {
        'Authorization': f'Bearer {accessToken}'
    }
    async with clientSession.get(url=baseURL, headers=headers) as resp:
        debug(f'Received response from Discord for user from access token: {accessToken}')
        
        # json encoded data returned
        data = await resp.json()
        debug('Response: ' + str(data))
        
        return data

# http://dev.fyicenter.com/1001053_Decode_Google_OpenID_Connect_id_token.html
async def getInfoFromEncodedGoogleIdToken(id_token):
    debug('Decoding id token to retrieve users google id...')
    # the id token is 3 base64 encoded strings delimited by a period, the header (0), the json (1), and the signature (2)
    base64EncodedJSON = id_token.split('.')[1]
    # google does not properly pad the base64 strings, so we need to add padding. normally this means doing something with a multiple of 4 characters, but we can just add the max number of padding and let the base64 decoder strip any unnecesary padding (as it is set to do by default)
    decodedJSON = base64.b64decode(base64EncodedJSON + '==')
    decodedDict = json.loads(decodedJSON)
    
    id = decodedDict.get('sub')
    name = decodedDict.get('name')
    profilePictureURL = decodedDict.get('picture')
    
    return (id, name, profilePictureURL)

# exchanges a code token for an authentication token and refresh token from discord API
# validates provided state variable against the one returned from discord
async def getDiscordCodeTokens(code, state, session: aiohttp_session.Session) -> str:
    debug(f'Getting refresh token using code: {code}')
    baseURL = 'https://discord.com/api/oauth2/token'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': sketchAuth.baseCallbackURL + 'discord/callback'
    }
    auth = aiohttp.BasicAuth(sketchAuth.discordClientID, sketchAuth.discordClientSecret)
    async with clientSession.post(url=baseURL, data=data, headers=headers, auth=auth) as resp:
        debug(f'Received response from Discord for tokens from code: {code}')
        # json encoded access token returned
        data = await resp.json()
        debug('Response: ' + str(data))
        
        if data and data.get('refresh_token') and data.get('access_token'):
            debug(f'refresh token: {data.get('refresh_token')}')
            debug(f'access token: {data.get('access_token')}')
            
            user = await getDiscordUser(data.get('access_token'))
            expiryDelta = datetime.timedelta(seconds=data.get('expires_in'))
            expiryDateTime = datetime.datetime.now(datetime.timezone.utc) + expiryDelta
            
            # store tokens, state, etc.
            dbUser, _ = await DiscordUser.get_or_create(id=user['id'])
            dbUser.name = user['global_name']
            dbUser.username = user['username']
            dbUser.accessToken = data.get('access_token')
            dbUser.refreshToken = data.get('refresh_token')
            dbUser.expiryTime = expiryDateTime
            dbUser.state = state
            dbUser.sessionID = session['sessionID']
            dbUser.profileImageURL = f'https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png'
            
            # Partial saves are now supported (#157): obj.save(update_fields=['model','field','names'])
            # https://github.com/tortoise/tortoise-orm/pull/165
            await DiscordUser.update_or_create(id=dbUser.id, defaults=dict(dbUser))
            
            session['expiryTime'] = expiryDateTime.isoformat()
            session['userID'] = user['id']
            
            result = f'<b class="success">Discord successfully authorized.</b><br>Hello, {dbUser.name}!'
        else:
            error('Response error: either no refresh token or access token provided. (or no JSON at all)')
            result = '<b class="error">Error: either no refresh token or access token provided. (or no JSON at all)</b>'
            
        return result

# https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps#exchange-authorization-code
# https://developers.google.com/identity/openid-connect/openid-connect#an-id-tokens-payload
async def getYoutubeTokens(code, state, session: aiohttp_session.Session) -> str:
    debug('Getting refresh token using code: ' + str(code))

    async with clientSession.post(
        "https://oauth2.googleapis.com/token" + 
        "?client_id=" + sketchAuth.ytClientID + 
        "&client_secret=" + sketchAuth.ytClientSecret + 
        "&code=" + code + 
        "&grant_type=authorization_code" + 
        "&redirect_uri=" + sketchAuth.baseCallbackURL + "youtube/callback"
    ) as resp:
        debug('Received response from YouTube for refresh token.')

        # json encoded access token returned
        data = await resp.json()
        debug('Response: ' + str(data))

        if data and data.get('refresh_token') and data.get('access_token'):
            debug(f'refresh token: {data.get('refresh_token')}')
            debug(f'access token: {data.get('access_token')}')
            
            expiryDelta = datetime.timedelta(seconds=data.get('expires_in'))
            expiryDateTime = datetime.datetime.now(datetime.timezone.utc) + expiryDelta
            
            id, name, profileImageURL = getInfoFromEncodedGoogleIdToken(data.get('id_token'))
            dbUser, _ = await YoutubeUser.get_or_create(id=id)
            dbUser.name = name
            dbUser.accessToken = data.get('access_token')
            dbUser.refreshToken = data.get('refresh_token')
            dbUser.expiryTime = expiryDateTime
            dbUser.profileImageURL = profileImageURL
            dbUser.state = state
            dbUser.sessionID = session.get('ytSessionID')
            
            await YoutubeUser.update_or_create(id=dbUser.id, defaults=dict(dbUser))
            
            session['ytExpiryTime'] = expiryDateTime.isoformat()
            session['ytUserID'] = id

            result = f'<b class="success">Youtube successfully authorized.</b><br>Thank you!'
        else:
            error('Response error: either no refresh token or access token provided. (or no JSON at all)')
            result = '<b class="error">Error: Youtube auth failed. Either no refresh token or access token provided. (or no JSON at all?)</b>'
        
        return result

# this should be used before making an authorized request, such as when trying to get the scheduled videos of a user. we can check that the user is authorized before calling this similar to validating the discord auth, but with ytSessionID and ytState from session object. right now this should never be called
# TODO: make this actually work
# https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps#offline
async def refreshYoutubeAccessToken(userID):
    # TODO code fallback for if refresh token becomes unusable (prompt re-authorization)
    #   - https://i.stack.imgur.com/Uf8KZ.png
    # what we should do is have this return True/False based on if it worked, and if it didn't, we can put an error message and ask the user to re-authorize youtube
    debug('Refreshing access token for userID: ' + str(userID))

    async with clientSession.post(
        "https://oauth2.googleapis.com/token" + 
        "?client_id=" + sketchAuth.ytClientID + 
        "&client_secret=" + sketchAuth.ytClientSecret + 
        "&grant_type=refresh_token" +
        "&refresh_token=" + sketchAuth.ytRefreshToken
    ) as resp:
        debug('Received response from YouTube for access token.')

        # json encoded access token returned
        data = await resp.json()
        debug('Response: ' + str(data))

        # TODO store these tokens in DB / associated with userID
        # TODO do something with the expires_in value returned
        if data and data.get('access_token'):
            debug('Refreshed access token for userID: ' + str(userID))

            sketchAuth.ytAccessToken = data.get('access_token')

            return True
        else:
            error("Request to refresh access token for userID: " + str(userID) + " failed: either no access token provided or no JSON at all.")

            return False

# validates user is logged in, validates session against database
async def validateDiscordAuth(session: aiohttp_session.Session, request: aiohttp.web.Request) -> DiscordUser | None:
    debug(f"Validating discord authentication for session: {session}")
    
    # if session has expiryTime, userID, state, and sessionID, then the user is authenticated.
    # checks if the dict is a subset of session, or in otherwords, that all of the values exist as keys
    if {'userID', 'sessionID', 'expiryTime', 'state'} <= set(session):
        # validate that it hasn't expired yet, and needs re-authentication
        # datetime has to come back from stored isoformat with fromisoformat()
        cookieExpiry = datetime.datetime.fromisoformat(session['expiryTime'])
        oneMinAgo = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
        if cookieExpiry <= oneMinAgo:
            # expired
            debug(f"Date from cookie: {cookieExpiry}")
            debug(f"Date from now: {oneMinAgo}")
            error("Session expired.")
            await newSession(request)
            return None

        # get the user from database
        dbUser = await DiscordUser.get_or_none(id=session['userID'])
        if not dbUser:
            error("Session not expired, but userID not found in database.")
            await newSession(request)
            return None
        
        # validate that the state, expiryTime, and sessionID match
        if session['sessionID'] != dbUser.sessionID or session['state'] != dbUser.state or session['expiryTime'] != dbUser.expiryTime.isoformat():
            error(f"state, expiryTime, or sessionID mismatch with database user: {await dbUser.all().values()}")
            if dbUser.expiryTime:
                debug(f"Cookie: {session['expiryTime']} Database: {dbUser.expiryTime.isoformat()}")
            await newSession(request)
            return None
        
        # generate a new state
        session['state'] = secrets.token_urlsafe(32)
        dbUser.state = session['state']
        await dbUser.save(update_fields=['state'])
        session.changed()
        
        debug(f"Created new state for authorized user: {session['state']}")
        
        return dbUser

    error("No user variables in session.")
    return None

# TODO create validateYoutubeAuth that is the same as discordAuth validation, but just removes the variables from the session cookie instead of making a new session

async def checkAuthorized(user: DiscordUser, guildID) -> bool:
    if not guildID:
        error(f"Checking authorization for discord user: {user.name} but guild was None")
        return False
    
    debug(f"Checking authorization for discord user: {user.name} and guild: {guildID}")
    
    dbGuild = await DiscordGuild.get(id=guildID)
    authorized = False
    if user.id == dbGuild.owner:
        authorized = True
    else:
        await dbGuild.fetch_related("authorizedUsers")
        for authorizedUser in dbGuild.authorizedUsers:
            if user.id == authorizedUser.id:
                authorized = True
                break

    return authorized

# MARK: EVENTS ------------------------------------------------------------------------------------------------------------

@subroutesDiscord.get('/')
async def discordLinkRedirect(request):
    debug('Redirecting to discord invite!')
    raise aiohttp.web.HTTPTemporaryRedirect("https://discord.com/invite/M4FdEDf")
    return aiohttp.web.Response(status=404)

@subroutesVoice.get('/')
async def voiceLinkRedirect(request):
    debug('Redirecting to voice!')
    raise aiohttp.web.HTTPTemporaryRedirect("https://www.youtube.com/watch?v=Y1xKsmzydqE")
    return aiohttp.web.Response(status=404)

# comment this out to hopefully not have to deal with the possibility that aiohttp parses an attack message? :(
@routes.get('/')
@aiohttp_jinja2.template('index.html')
async def hello(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    messages = await getMessages(session)    
    csrfToken = await aiohttp_csrf.generate_token(request)
    user = await validateDiscordAuth(session, request)

    return {'messages': messages,'csrfToken': csrfToken, 'user': user}

@routes.get('/admin/logs')
@aiohttp_jinja2.template('logs.html')
async def logs(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    messages = await getMessages(session)    
    csrfToken = await aiohttp_csrf.generate_token(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        if user.id == sketchAuth.discordOwner:
            with open('./logs/sketch.log', 'r') as f:
                text = f.read().replace('\\n', '\n')
            return {'messages': messages,'csrfToken': csrfToken, 'user': user, 'text': text}
    
    return aiohttp.web.HTTPSeeOther('/')

@routes.get('/login')
@aiohttp_jinja2.template('login.html')
async def login(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    messages = await getMessages(session)    
    csrfToken = await aiohttp_csrf.generate_token(request)
    user = await validateDiscordAuth(session, request)

    return {'messages': messages,'csrfToken': csrfToken, 'user': user}

@routes.get('/discord')
@aiohttp_jinja2.template('discord.html')
async def discord(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    messages = await getMessages(session)    
    csrfToken = await aiohttp_csrf.generate_token(request)
    user = await validateDiscordAuth(session, request)
    
    guilds = set()
    discordGuilds = {}
    if user:
        ownedGuilds = await DiscordGuild.filter(owner=user.id)
        for guild in ownedGuilds:
            await guild.fetch_related('twitchAnnouncements')
            await guild.fetch_related('authorizedUsers')
            await guild.fetch_related('joinRoles')
            discordGuilds[guild.id] = sketchDiscord.bot.get_guild(guild.id)
            guilds.add(guild)
        for guild in await user.authorizedGuilds.all():
            await guild.fetch_related('twitchAnnouncements')
            await guild.fetch_related('authorizedUsers')
            await guild.fetch_related('joinRoles')
            discordGuilds[guild.id] = sketchDiscord.bot.get_guild(guild.id)
            guilds.add(guild)

    return {'messages': messages,'csrfToken': csrfToken, 'user': user, 'guilds': guilds, 'discordGuilds': discordGuilds}

# /discord/config
@routes.post('/discord/config')
async def updateDiscordConfig(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        authorized = await checkAuthorized(user, data.get('guild'))
        
        if not authorized:
            session['messages'].append(f'''<b class="error">Failed updating guild config. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
        else:
            dbGuild = await DiscordGuild.get(id=data.get('guild'))
            
            dbGuild.deleteOldAnnouncements = True if data.get('deleteOldAnnouncements') == 'True' else False
            
            try:
                if not data.get('spamProtectionAnnounceDelay'):
                    num = 0
                else:
                    num = int(float(data.get('spamProtectionAnnounceDelay')))
            except ValueError:
                num = dbGuild.spamProtectionAnnounceDelay
                session['messages'].append(f'''<b class="error">Invalid Re-Announce Delay. (Must be a number.)</b><br>Re-Announce Delay not changed. Please try again, or contact alastairvox on discord.''')
            dbGuild.spamProtectionAnnounceDelay = num
            
            try:
                pytz.timezone(data.get('timeZone'))
                timeZone = data.get('timeZone')
            except pytz.exceptions.UnknownTimeZoneError:
                timeZone = dbGuild.timeZone
                session['messages'].append(f'''<b class="error">Invalid Time Zone. (Must be from <a href="https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568">list.</a>)</b><br>Time Zone not changed. Please try again, or contact alastairvox on discord.''')
            dbGuild.timeZone = timeZone
            
            await dbGuild.save(update_fields=['timeZone', 'spamProtectionAnnounceDelay', 'deleteOldAnnouncements'])
            session['messages'].append(f'<b class="success">Guild config updated.</b><br>Guild: {dbGuild.name}')
            
    return aiohttp.web.HTTPSeeOther('/discord')

# /discord/authorizedUser/add
@routes.post('/discord/authorizedUser/add')
async def addDiscordAuthorizedUser(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        authorized = await checkAuthorized(user, data.get('guild'))
        
        if not authorized:
            session['messages'].append(f'''<b class="error">Failed adding authorized user. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
        else:
            dbUsers = []
            for authUser in data.getall('users'):
                dbUser, _ = await DiscordUser.get_or_create(id=authUser)
                discordUser = await sketchDiscord.bot.fetch_user(dbUser.id)
                dbUser.name = discordUser.global_name
                dbUser.username = discordUser.name
                await dbUser.save()
                dbUsers.append(dbUser)
            
            if dbUsers:
                dbGuild = await DiscordGuild.get(id=data.get('guild'))
                await dbGuild.authorizedUsers.add(*dbUsers)
            session['messages'].append(f'<b class="success">Users authorized.</b><br>Users: {[addedUser.username for addedUser in dbUsers]}')
    
    return aiohttp.web.HTTPSeeOther('/discord')
            
# /discord/authorizedUser/delete
@routes.post('/discord/authorizedUser/delete')
async def deleteDiscordAuthorizedUser(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        authorized = await checkAuthorized(user, data.get('guild'))
        
        if not authorized:
            session['messages'].append(f'''<b class="error">Failed removing authorized user. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
        else:
            # passes guild and userID
            dbGuild = await DiscordGuild.get_or_none(id=data.get('guild'))
            dbUser = await DiscordUser.get_or_none(id=data.get('userID'))
            if not dbGuild or not dbUser:
                session['messages'].append(f'''<b class="error">Failed removing authorized user. (User or guild couldn't be fetched from database.)</b><br>Please try again, or contact alastairvox on discord.''')
            else:
                await dbGuild.authorizedUsers.remove(dbUser)
                session['messages'].append(f'<b class="success">Authorized user removed.</b><br>User: {dbUser.username}')
        
    return aiohttp.web.HTTPSeeOther('/discord')

# /discord/joinRole/add
@routes.post('/discord/joinRole/add')
async def addDiscordJoinRole(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        authorized = await checkAuthorized(user, data.get('guild'))
        
        if not authorized:
            session['messages'].append(f'''<b class="error">Failed adding Join Role. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
        else:
            dbGuild = await DiscordGuild.get(id=data.get('guild'))
            discordGuild = sketchDiscord.bot.get_guild(dbGuild.id)
            
            dbRoles = []
            for joinRole in data.getall('roles'):
                discordRole = discordGuild.get_role(int(joinRole))
                if not discordRole:
                    session['messages'].append(f'''<b class="error">Failed adding join role. (Role ID not found on server.)</b><br>Role: {joinRole} Please try again, or contact alastairvox on discord.''')
                else:
                    dbRole, _ = await DiscordJoinRole.get_or_create(id=joinRole, guild=dbGuild)
                    dbRole.name = discordRole.name
                    dbRole.guild = dbGuild
                    await dbRole.save()
                    dbRoles.append(dbRole)
            
            session['messages'].append(f'<b class="success">Join Roles added.</b><br>Roles: {[addedRole.name + ' (' + str(addedRole.id) + ')' for addedRole in dbRoles]}')
    return aiohttp.web.HTTPSeeOther('/discord')

# /discord/joinRole/delete
@routes.post('/discord/joinRole/delete')
async def deleteDiscordJoinRole(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        role = await DiscordJoinRole.get_or_none(id=data.get('roleID'))
        if not role:
            session['messages'].append(f'<b class="error">Failed deleting Join Role. (Invalid role ID.)</b><br>Please try again, or contact alastairvox on discord.')
        else:
            await role.fetch_related('guild')
            authorized = await checkAuthorized(user, role.guild.id)
    
            if not authorized:
                session['messages'].append(f'''<b class="error">Failed deleting Join Role. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
            else:
                await role.delete()
                session['messages'].append(f'<b class="success">Join Role deleted.</b><br>Role: {role.name} ({role.id})')
    
    return aiohttp.web.HTTPSeeOther('/discord')

@routes.post('/discord/announcement/add')
async def addDiscordAnnouncement(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        authorized = await checkAuthorized(user, data.get('guild'))
        
        if not authorized:
            session['messages'].append(f'''<b class="error">Failed creating Twitch announcement. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
        else:
            streamUser = await sketchTwitch.bot.fetch_user(login=data.get('streamName'))
            if not streamUser:
                # no channel by that name, error
                session['messages'].append(f'<b class="error">Failed creating Twitch announcement. (No channel by that name on Twitch.)</b><br>Please try again, or contact alastairvox on discord.')
            else:
                dbGuild = await DiscordGuild.get(id=data.get('guild'))
                await TwitchAnnouncement.create(streamName=data.get('streamName'),
                                                streamID=streamUser.id,
                                                announcementText=data.get('announcementText'),
                                                guild=dbGuild,
                                                channelID=data.get('channel'))
                session['messages'].append(f'<b class="success">Twitch announcement created.</b><br>Stream: {data.get('streamName')}')
        
    return aiohttp.web.HTTPSeeOther('/discord')

@routes.post('/discord/announcement/delete')
async def deleteDiscordAnnouncement(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        announcement = await TwitchAnnouncement.get_or_none(id=data.get('announcementID'))
        if not announcement:
            session['messages'].append(f'<b class="error">Failed deleting Twitch announcement. (Invalid announcement ID.)</b><br>Please try again, or contact alastairvox on discord.')
        else:
            await announcement.fetch_related('guild')
            authorized = await checkAuthorized(user, announcement.guild.id)
    
            if not authorized:
                session['messages'].append(f'''<b class="error">Failed deleting Twitch announcement. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
            else:
                await announcement.delete()
                session['messages'].append(f'<b class="success">Twitch announcement deleted.</b><br>Stream: {data.get('streamName')}')
            
    return aiohttp.web.HTTPSeeOther('/discord')
    
@routes.post('/discord/announcement/edit')
async def updateDiscordAnnouncement(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        announcement = await TwitchAnnouncement.get_or_none(id=data.get('announcementID'))
        if not announcement:
            session['messages'].append(f'<b class="error">Failed editing Twitch announcement. (Invalid announcement ID.)</b><br>Please try again, or contact alastairvox on discord.')
        else:
            streamUser = await sketchTwitch.bot.fetch_user(login=data.get('streamName'))
            if not streamUser:
                # no channel by that name, error
                session['messages'].append(f'<b class="error">Failed editing Twitch announcement. (No channel by that name on Twitch.)</b><br>Please try again, or contact alastairvox on discord.')
            else:
                await announcement.fetch_related('guild')
                authorized = await checkAuthorized(user, announcement.guild.id)
        
                if not authorized:
                    session['messages'].append(f'''<b class="error">Failed editing Twitch announcement. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
                else:
                    announcement.streamName=data.get('streamName')
                    announcement.streamID=streamUser.id
                    announcement.announcementText=data.get('announcementText')
                    announcement.channelID=data.get('channel')
                    await announcement.save()
                    session['messages'].append(f'<b class="success">Twitch announcement edited.</b><br>Stream: {data.get('streamName')}')

    return aiohttp.web.HTTPSeeOther('/discord')

# youtubeChannel = 'UCGPBgBHGdmr1VSaK_3Oitqw' # various artists - topic
# youtubeChannel = 'UC-lHJZR3Gqxm24_Vd_AJ5Yw' # pewdiepie
@routes.post('/discord/ytannouncement/add')
async def addDiscordYTAnnouncement(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        authorized = await checkAuthorized(user, data.get('guild'))
        
        if not authorized:
            session['messages'].append(f'''<b class="error">Failed creating Youtube announcement. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
        else:
            ytChannel, _ = await YoutubeChannel.get_or_create(id=data.get('ytChannelID'))
            
            dbGuild = await DiscordGuild.get(id=data.get('guild'))
            announcement = await YoutubeAnnouncement.create(
                channelID=data.get('channel'),
                announcementText=data.get('announcementText'),
                youtubeChannel=ytChannel,
                guild=dbGuild
            )
            
            if not ytChannel.announcedVideos:
                responseStatus = await sketchYoutube.gatherYoutubeVideos(ytChannel)
                if responseStatus != 200:
                    session['messages'].append(f'<b class="error">Failed creating Youtube announcement. (Error {responseStatus} when attempting to get {data.get('ytChannelID')} from YouTube. Make sure you have provided a valid YouTube channel ID (like UC_0hyh6_G3Ct1k1EiqaorqQ).)</b><br>Please try again, or contact alastairvox on discord.')
                    announcement.delete()
                    ytChannel.delete()
                    return aiohttp.web.HTTPSeeOther('/discord')
                else:
                    responseStatus = await sketchYoutube.subscribeToYoutubeUploads(ytChannel)
                    if responseStatus != 202:
                        session['messages'].append(f'<b class="error">Failed creating Youtube announcement. (Error {responseStatus} when attempting to get {data.get('ytChannelID')} from YouTube. Make sure you have provided a valid YouTube channel ID (like UC_0hyh6_G3Ct1k1EiqaorqQ).)</b><br>Please try again, or contact alastairvox on discord.')
                        announcement.delete()
                        ytChannel.delete()
                        return aiohttp.web.HTTPSeeOther('/discord')
            
            session['messages'].append(f'<b class="success">Youtube announcement created.</b><br>Channel: {data.get('ytChannelID')}')
            
    return aiohttp.web.HTTPSeeOther('/discord')

# if deleting the last announcement for a channel, delete the channel as well so it doesn't get it's subscriptions renewed
@routes.post('/discord/ytannouncement/delete')
async def deleteDiscordYTAnnouncement(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        announcement = await YoutubeAnnouncement.get_or_none(id=data.get('announcementID'))
        if not announcement:
            session['messages'].append(f'<b class="error">Failed deleting Youtube announcement. (Invalid announcement ID.)</b><br>Please try again, or contact alastairvox on discord.')
        else:
            await announcement.fetch_related("youtubeChannel", "guild")
            authorized = await checkAuthorized(user, announcement.guild.id)
    
            if not authorized:
                session['messages'].append(f'''<b class="error">Failed deleting Youtube announcement. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
            else:
                await announcement.fetch_related('youtubeChannel')
                oldChannel = announcement.youtubeChannel
                info(f'deleting announcement from db {announcement.id}')
                await announcement.delete()
                await oldChannel.refresh_from_db()
                await oldChannel.fetch_related("youtubeAnnouncements")
                
                if not oldChannel.youtubeAnnouncements:
                    info(f'deleting last announcement from ytChannel {announcement.youtubeChannel.id}')
                    await oldChannel.delete()
                    
                session['messages'].append(f'<b class="success">Youtube announcement deleted.</b><br>Channel: {data.get('ytChannelID')}')
            
    return aiohttp.web.HTTPSeeOther('/discord')
    
@routes.post('/discord/ytannouncement/edit')
async def updateDiscordYTAnnouncement(request: aiohttp.web.Request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + str(await request.text()) +
    ' thats it :)')
    
    session = await getSession(request)
    user = await validateDiscordAuth(session, request)
    
    if user:
        data = await request.post()
        debug(data)
        
        announcement = await YoutubeAnnouncement.get_or_none(id=data.get('announcementID'))
        if not announcement:
            session['messages'].append(f'<b class="error">Failed editing Youtube announcement. (Invalid announcement ID.)</b><br>Please try again, or contact alastairvox on discord.')
        else:
            await announcement.fetch_related("youtubeChannel", "guild")
            authorized = await checkAuthorized(user, announcement.guild.id)
    
            if not authorized:
                session['messages'].append(f'''<b class="error">Failed editing Youtube announcement. (You are not in guild's authorized user list.)</b><br>Please try again, or contact alastairvox on discord.''')
                return aiohttp.web.HTTPSeeOther('/discord')
            else:
                ytChannel, _ = await YoutubeChannel.get_or_create(id=data.get('ytChannelID'))
                
                oldChannel = None
                if data.get('ytChannelID') != announcement.youtubeChannel.id:
                    oldChannel = announcement.youtubeChannel

                announcement.youtubeChannel = ytChannel
                announcement.announcementText = data.get('announcementText')
                announcement.channelID = data.get('channel')
                await announcement.save()
                
                if not ytChannel.announcedVideos:
                    responseStatus = await sketchYoutube.gatherYoutubeVideos(ytChannel)
                    if responseStatus != 200:
                        session['messages'].append(f'<b class="error">Failed updating Youtube announcement. (Error {responseStatus} when attempting to get {data.get('ytChannelID')} from YouTube. Make sure you have provided a valid YouTube channel ID (like UC_0hyh6_G3Ct1k1EiqaorqQ).)</b><br>Please try again, or contact alastairvox on discord.')
                        if oldChannel:
                            announcement.youtubeChannel = oldChannel
                            await announcement.save()
                        ytChannel.delete()
                        return aiohttp.web.HTTPSeeOther('/discord')
                    else:
                        responseStatus = await sketchYoutube.subscribeToYoutubeUploads(ytChannel)
                        if responseStatus != 202:
                            session['messages'].append(f'<b class="error">Failed updating Youtube announcement. (Error {responseStatus} when attempting to get {data.get('ytChannelID')} from YouTube. Make sure you have provided a valid YouTube channel ID (like UC_0hyh6_G3Ct1k1EiqaorqQ).)</b><br>Please try again, or contact alastairvox on discord.')
                            if oldChannel:
                                announcement.youtubeChannel = oldChannel
                                await announcement.save()
                            ytChannel.delete()
                            return aiohttp.web.HTTPSeeOther('/discord')
                
                if oldChannel:
                    await oldChannel.refresh_from_db()
                    await oldChannel.fetch_related("youtubeAnnouncements")
                    # check if that channel now has no announcements
                    if not oldChannel.youtubeAnnouncements:
                        info(f'removing last announcement from ytChannel {oldChannel.id}')
                        await oldChannel.delete()
                
                session['messages'].append(f'<b class="success">Twitch announcement edited.</b><br>Channel: {data.get('ytChannelID')}')

    return aiohttp.web.HTTPSeeOther('/discord')


# start discord authentication for user
# store the refresh token, access token, expiry time, state, and sessionid in database
# store the expiry time, user id, and state (random code) in the encrypted session cookie (sessionid already there)
# check the data from the cookie (session id, state, user id, expiry time) matches correctly when changing any configuration, or else clear their session data, send them to the login page
@routes.get('/discord/auth')
async def login(request: aiohttp.web.Request):
    info(f'Redirecting {str(request.remote)} to Discord to begin authentication...')
    session = await newSession(request)
    debug(f'Session has ID {session['sessionID']}')
    
    session['state'] = secrets.token_urlsafe(32) + '::sketch::' + session['sessionID']
    
    baseURL = 'https://discord.com/oauth2/authorize'
    
    params = {'client_id': sketchAuth.discordClientID,
              'scope': 'identify',
              'response_type': 'code',
              'redirect_uri': sketchAuth.baseCallbackURL + 'discord/callback',
              'state': session['state'],
              'prompt': 'none'}
    
    params = urlencode(params)
    
    # 307 response
    raise aiohttp.web.HTTPTemporaryRedirect(location=baseURL+'?'+params)

# validate state against cookie, handle code from query
@routes.get('/discord/callback')
async def discordCallback(request: aiohttp.web.Request):
    info('Responding to Discord callback request.')
    session = await getSession(request)
    debug(f'Session has ID {session['sessionID']}')

    if 'code' not in request.query or 'state' not in request.query:
        error('Discord callback request did not contain either state or code query attributes.')
        
        if 'error' in request.query:
            errorMessage = str(request.query['error'])
            error('Error: ' + errorMessage)
            session['messages'].append(f'<b class="error">Error: Something went wrong with Discord authorization. ({errorMessage})</b><br>Please try again, or contact alastairvox on discord.')
            session.changed()
            
        else:
            error('No error provided: attempted attack? Discord should always provide an error. Request: ' + str(request))
            session['messages'].append('<b class="error">Error: Something went wrong with Discord authorization. (Unknown Error)</b><br>Please try again, or contact alastairvox on discord.')
            session.changed()
    else:
        state = str(request.query['state'])
        code = str(request.query['code'])
        # validate state, then use code query attribute to request and store refresh token
        debug(f'Request has code: {code} and state: {state}')
        
        debug('Validating state...')
        if state != str(session['state']):
            error(f'Discord callback request state mismatch. Cookie state: {str(session['state'])} and request state: {state}')
            session['messages'].append(f'<b class="error">Error: Something went wrong with Discord authorization. (Invalid State)</b><br>Please try again, or contact alastairvox on discord.')
            session.changed()
        else:
            result = await getDiscordCodeTokens(request.query['code'], request.query['state'], session)
            session['messages'].append(result)
            session.changed()
    
    # 303 response
    raise aiohttp.web.HTTPSeeOther('/login')

# redirects user to google's oauth endpoint to begin oauth flow
# https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps#httprest_1
@routes.get('/youtube/auth')
async def youtubeAuth(request: aiohttp.web.Request):
    info(f'Redirecting {str(request.remote)} to Youtube to begin authentication...')
    session = await getSession(request)
    
    newUUID = str(uuid.uuid4())
    session['ytSessionID'] = str(newUUID)
    
    debug(f'Session has ID {session['ytSessionID']}')
    
    session['ytState'] = secrets.token_urlsafe(32) + '::sketch::' + session['ytSessionID']

    scopes = 'openid https://www.googleapis.com/auth/youtube.force-ssl'

    raise aiohttp.web.HTTPTemporaryRedirect("https://accounts.google.com/o/oauth2/v2/auth" + 
    "?client_id=" + sketchAuth.ytClientID + 
    "&redirect_uri=" + sketchAuth.baseCallbackURL + "youtube/callback" + 
    "&response_type=code" + 
    "&scope=" + scopes + 
    "&access_type=offline" + 
    "&state=" + str(session['ytState']) + 
    "&include_granted_scopes=true")

# receives return info from google's oauth endpoint
# https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps#handlingresponse
@routes.get('/youtube/callback')
async def youtubeCallback(request: aiohttp.web.Request):
    info('Responding to YouTube callback request.')
    session = await getSession(request)
    debug(f'Session has ID {session.get('ytSessionID')}')

    if 'code' not in request.query or 'state' not in request.query:
        error('YouTube callback request did not contain either state or code query attributes.')

        if 'error' in request.query:
            errorMessage = str(request.query['error'])
            error('Error: ' + errorMessage)
            session['messages'].append(f'<b class="error">Error: Something went wrong with Youtube authorization. ({errorMessage})</b><br>Please try again, or contact alastairvox on discord.')
            session.changed()
        
        else:
            error('No error provided: attempted attack? Youtube should always provide an error. Request: ' + str(request))
            session['messages'].append('<b class="error">Error: Something went wrong with Youtube authorization. (Unknown Error)</b><br>Please try again, or contact alastairvox on discord.')
            session.changed()
    else:
        # use code query attribute to request and store refresh token
        info('Received YouTube callback, getting tokens (refresh, access, id)')
        state = str(request.query['state'])
        code = str(request.query['code'])
        # validate state, then use code query attribute to request and store refresh token
        debug(f'Request has code: {code} and state: {state}')
        
        debug('Validating state...')
        if state != str(session.get('ytState')):
            error(f'Youtube callback request state mismatch. Cookie state: {str(session.get('ytState'))} and request state: {state}')
            session['messages'].append(f'<b class="error">Error: Something went wrong with Youtube authorization. (Invalid State)</b><br>Please try again, or contact alastairvox on discord.')
            session.changed()
        else:
            result = await getYoutubeTokens(request.query['code'], request.query['state'], session)
            session['messages'].append(result)
            session.changed()
    
    raise aiohttp.web.HTTPSeeOther('/discord')

# called by the hub to establish a new lease when subscribing to youtube uploads
@routes.get('/youtube/{ytChannelID}')
async def youtube(request: aiohttp.web.Request):
    debug(f'Responding to {request}')
    if hasattr(request, 'query'):
        channel = request.query.get('hub.topic')
        if channel:
            channel = channel.split('channel_id=')[1]   # [0] = the url https://www.youtube.com/xml/feeds/videos.xml? or any params that came before the channel_id param, [1] = the channel id and any params that come after the channel_id
            channel = channel.split('&')[0]             # [0] = the channel id [1]+ = other params that came after channel_id
        
        hubChallenge = request.query.get('hub.challenge')
        if request.query.get('hub.lease_seconds'):
            leaseSeconds = int(request.query.get('hub.lease_seconds'))-90
        else:
            leaseSeconds = None

        if channel and hubChallenge and leaseSeconds:
            # store them in youtube config, we'll check later to see if we need to renew by by finding the difference between the time it was stored and the time it is now in seconds and seeing if >= leaseSeconds and if it is then resubscribe
            updates = {
                'leaseSeconds': leaseSeconds,
                'time': datetime.datetime.now(datetime.timezone.utc)
            }
            dbChannel, _ = await YoutubeChannel.update_or_create(id=channel, defaults=updates)
            
            # CALL FUNCTION THAT AWAITS SLEEP FOR THE NUMBER OF SECONDS EQUAL TO the stored leaseSeconds (because i subtract 90 when storing) then calls the resubscribe, make a function that will look through all the stored youtube channels when discord starts, and calls the same function for each channel that has a leaseSeconds stored
            loop = asyncio.get_event_loop()
            loop.create_task(sketchYoutube.youtubeWaitForResub(leaseSeconds, dbChannel))
            info(f'Lease aquired for channel {channel}')
            return aiohttp.web.Response(status=200, text=hubChallenge)
        else:
            error(f'missing channel, challenge or lease: {await request.text()}')
            return aiohttp.web.Response(status=404, text="missing channel, challenge or lease")
    else:
        error('Youtube request has no query attribute!')
        error(await request.text())
        return aiohttp.web.Response(status=404, text="what are you doing")


@routes.post('/youtube/{ytChannelID}')
@aiohttp_csrf.csrf_exempt
async def youtubeUploadedNotification(request: aiohttp.web.Request):
    ytChannelID = request.match_info['ytChannelID']
    # store a copy of the youtube video number so i dont re-announce youtube videos if they just get updated: have to parse the xml of the text out for relevant bits
    # pass the text (xml, xml.etree.ElementTree?) to a discord function that parses out the author name, video title, URL (<link rel="alternate" href="), and the time published and then announces the stream
    debug(f'Responding to {request} for {ytChannelID}')
    # we add this to the end of the event loop so that we can return a response to the request right away, allowing us to respond and then process the data later
    loop = asyncio.get_event_loop()
    loop.create_task(sketchDiscord.announceYoutubeUpload(await request.read()))
    return aiohttp.web.Response(status=200)

@routes.post('/test')
async def test(request: aiohttp.web.Request):
    debug('Testing...')

    # await sketchDatabase.SketchDbObj.create('youtubeVideos', {'videoId': '7t5a32SRf-s', 'channelId': 'UCmkonxPPduKnLNWvqhoHl_g', 'title': 'short clips', 'privacyStatus': 'private', 'thumbnailUrl': 'https://i9.ytimg.com/vi/7t5a32SRf-s/hqdefault.jpg?sqp=CPjupqQG&rs=AOn4CLAeWYaTGi_N33HYRUDWNxpMEOu3gw'})

    result = await sketchDiscord.test()
    
    session = await getSession(request)
    session['messages'].extend([result, result])
    session.changed()

    debug(session)
    
    return aiohttp.web.HTTPSeeOther('/')