import sketchShared
from sketchShared import debug, info, warn, error, critical
import asyncio, aiohttp, aiohttp.web, logging
import sketchAuth, sketchYoutube, sketchDatabase

# ---------- SETUP -------------------------------------------------------------------------------------------------------------
# ---------- SETUP -------------------------------------------------------------------------------------------------------------
# ---------- SETUP -------------------------------------------------------------------------------------------------------------

async def startServer():
    info('Starting server...')
    
    app.add_routes(routes)

    loop = asyncio.get_event_loop()
    #  uses internal _run_app since we are managing our own loops
    loop.create_task(aiohttp.web._run_app(app, port=sketchAuth.callbackPort, print=None))

async def on_startup(app):
    info('Connected to HTTP server on port ' + sketchAuth.callbackPort + '.')

    # TODO disable/remove this for "production"
    logging.getLogger("aiohttp.access").setLevel(logging.WARN)

    await test('')

async def on_shutdown(app):
    info('Disconnected from HTTP server on port ' + sketchAuth.callbackPort + '.')

routes = aiohttp.web.RouteTableDef()
app = aiohttp.web.Application()
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)
session = aiohttp.ClientSession()

# ---------- FUNCTIONS ---------------------------------------------------------------------------------------------------------
# ---------- FUNCTIONS ---------------------------------------------------------------------------------------------------------
# ---------- FUNCTIONS ---------------------------------------------------------------------------------------------------------

# ---------- EVENTS ------------------------------------------------------------------------------------------------------------
# ---------- EVENTS ------------------------------------------------------------------------------------------------------------
# ---------- EVENTS ------------------------------------------------------------------------------------------------------------

# comment this out to hopefully not have to deal with the possibility that aiohttp parses an attack message :(
@routes.get('/')
async def hello(request):
    debug('Responding to ' + str(request) +
    ' from ' + str(request.remote) +
    ' headers ' + str(request.headers) +
    ' body ' + await str(request.text()))

    return aiohttp.web.Response(status=404)

# redirects user to google's oauth endpoint to begin oauth flow
# https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps#httprest_1
@routes.get('/youtube/auth/{userID}')
async def youtubeAuth(request):
    userID = request.match_info.get('userID', '')

    debug('Responding to YouTube OAuth request for user: ' + str(userID))

    # TODO search database for this yt userID and see if it exists and is waiting for auth
    #   - stop using 'True'
    userFound = True

    # if we have an entry for this user and are waiting for them to authenticate
    if userFound:
        info('Redirecting user to YouTube auth page, userID ' + str(userID) + ' found in database.')

        scopes = 'openid https://www.googleapis.com/auth/youtube.force-ssl'

        raise aiohttp.web.HTTPTemporaryRedirect("https://accounts.google.com/o/oauth2/v2/auth" + 
        "?client_id=" + sketchAuth.ytClientID + 
        "&redirect_uri=" + sketchAuth.callbackAddress + "youtube/callback" + 
        "&response_type=code" + 
        "&scope=" + scopes + 
        "&access_type=offline" + 
        "&state=" + str(userID) + 
        "&include_granted_scopes=true")
    else:
        error('userID ' + str(userID) + ' not found in database.')
        
        return aiohttp.web.Response(text="""<div style="height: 100%; display: flex; justify-content: center; align-items: center">
            <div>
                <b>Error: This user is not waiting to authenticate.</b>
            </div>
        </div>""", content_type="text/html")

# receives return info from google's oauth endpoint
# https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps#handlingresponse
@routes.get('/youtube/callback')
async def youtubeCallback(request):
    debug('Responding to YouTube callback request.')

    if 'code' not in request.query or 'state' not in request.query:
        error('YouTube callback request did not contain either state or code query attributes.')

        if 'error' in request.query:
            error('Error: ' + str(request.query['error']))
            
            result = """<div style="height: 100%; display: flex; justify-content: center; align-items: center">
                <div>
                    <b>Error: Something went wrong with YouTube authorization. (""" + request.query['error'] + """)</b>
                    <br>Please try again, or contact alastairvox on discord.
                </div>
            </div>"""
        else:
            error('No error provided: attempted attack? Youtube should always provide an error. Request: ' + str(request))

            result = """<div style="height: 100%; display: flex; justify-content: center; align-items: center">
                <div>
                    <b>Error: Something went wrong with YouTube authorization. (Unknown Error)</b>
                    <br>Please try again, or contact alastairvox on discord.
                </div>
            </div>"""
    else:
        # use code query attribute to request and store refresh token
        info('Received YouTube callback, getting tokens (refresh, access, id) for userID ' + str(request.query['state']))
        debug('Request has code: ' + str(request.query['code']))
        
        result = await sketchYoutube.getYoutubeTokens(request.query['code'], request.query['state'])
    
    return aiohttp.web.Response(text=result, content_type="text/html")

@routes.get('/test')
async def test(request):
    debug('Testing...')

    await sketchDatabase.createDatabase()

    # await sketchDatabase.SketchDbObj.create('youtubeVideos', {'videoId': '7t5a32SRf-s', 'channelId': 'UCmkonxPPduKnLNWvqhoHl_g', 'title': 'short clips', 'privacyStatus': 'private', 'thumbnailUrl': 'https://i9.ytimg.com/vi/7t5a32SRf-s/hqdefault.jpg?sqp=CPjupqQG&rs=AOn4CLAeWYaTGi_N33HYRUDWNxpMEOu3gw'})

    return aiohttp.web.Response(text="testing", content_type="text/html")