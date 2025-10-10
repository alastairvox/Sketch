import sketchShared
from sketchShared import debug, info, warn, error, critical
import twitchio, twitchio.ext.commands, asyncio, traceback
import sketchAuth, sketchDiscord
from sketchModels import *

# MARK: SETUP -------------------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------

bot = twitchio.ext.commands.Bot(
        client_id=sketchAuth.twitchClientID,
        client_secret=sketchAuth.twitchClientSecret,
        bot_id=sketchAuth.twitchBotID,
        owner_id=sketchAuth.twitchOwnerID,
        prefix='!'
    )

# starts the bot when called
async def summon():
    info("Summoning...")
    loop = asyncio.get_running_loop()
    loop.create_task(checkStreams())
    await bot.start()
    

# MARK: FUNCTIONS ---------------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------

async def checkStreams():
    while True:
        try:
            if sketchShared.dev:
                await asyncio.sleep(7)
            else:
                await asyncio.sleep(30)
            
            await bot.wait_until_ready()
            await sketchDiscord.bot.wait_until_ready()

            streamsToCheck = await getStreamsToCheck()
            if not streamsToCheck:
                # restarts the loop from the top (so waits, then checks again)
                continue
            
            try:
                response = await bot.fetch_streams(user_ids=[stream.streamID for stream in streamsToCheck], first=100)
            except twitchio.HTTPException as error:
                error('HTTPException getting stream information: ' + str(error))
                continue
            else:
                await notifyStreams(response)
        
        except Exception as error:
            error(traceback.print_exc())
            continue
        
async def getStreamsToCheck() -> list[TwitchAnnouncement]:
    streams = []
    for stream in await TwitchAnnouncement.filter(streamID__not_isnull=True):
        if stream in streams:
            # stream already added, next stream
            continue
        # includes announcements that have a message already, and ones that don't
        streams.append(stream)
    return streams

async def notifyStreams(streams: list[twitchio.Stream]):
    streamIDs = []
    streamsToAnnounce = []
    games = []
    users = []
    for stream in streams:
        streamIDs.append(stream.id)
        
    for announcement in await TwitchAnnouncement.filter(streamID__not_isnull=True):
        messageID = announcement.messageID
        streamID = str(announcement.streamID)
        if not messageID and streamID in streamIDs:
            # stream has no announcement, but is in the list of live streams, so announce
            # because the streamIDs list is made from the streams list, the stream object is at the same index as the ID
            stream = streams[streamIDs.index(streamID)]
            if stream.game_id:
                # add the game to a list so that we can get the game image and etc. from twitch later
                games.append(stream.game_id)
            # add the user to a list so we can get their profile image and etc. from twitch later
            users.append(streamID)
            # associate the db entry and the twitchio stream object, so we can reference both later
            streamsToAnnounce.append({'dbStream': announcement, 'twitchioStream': stream})
        elif messageID and streamID not in streamIDs:
            # stream had an announcement, but is not in the list of live streams, so remove/edit its announcement
            # if the stream doesn't have an "ended" attribute, then it isn't being delayed due to spam ping protection, so log that it's newly offline
            if not announcement.ended:
                info(announcement.streamName + ' went offline...')
            await sketchDiscord.removeAnnouncement(announcement, stream)
        elif messageID and streamID in streamIDs and announcement.ended:
            # going live, but there's an "ended" entry for the stream, so removal was being delayed due to spam ping protection and they went live again within the time limit
            info(announcement.streamName + ' went live again within grace period.')
            announcement.ended = None
            announcement.save(update_fields=['ended'])
            
    # get information about the games that are being played, including game name and game image
    if games:
        games = await bot.fetch_games(ids=games)

    # get information about the users being announced, including profile image and the user offline image
    if users:
        # cannot fetch more than 100 users at a time...
        fullUsers: list[twitchio.User] = []
        for i in range(0, len(users), 100):
            # slicing beyond the end of the list gets the remaining items correctly (no errors)
            subList = users[i:i+100]
            response = await bot.fetch_users(ids=subList)
            fullUsers.extend(response)
        for user in fullUsers:
            await TwitchAnnouncement.filter(streamID=user.id).update(profileImageURL=user.profile_image.base_url, offlineImageURL=user.offline_image.base_url)
    
    for stream in streamsToAnnounce: 
        game = {'name': 'No Game or Unknown'}
        for gameResponse in games:
            if stream['twitchioStream'].id == gameResponse.id:
                game = gameResponse
                break
        info(stream['dbStream'].streamName + ' is live unannounced...')
        await sketchDiscord.makeAnnouncement(stream['dbStream'], stream['twitchioStream'], game)