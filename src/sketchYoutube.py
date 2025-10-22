import sketchShared
from sketchShared import debug, info, warn, error, critical
import asyncio, datetime, dateutil
import sketchAuth, sketchServer
from sketchModels import *

# sketchServer: endpoints to receive YT oauth2 & pubsub
#   - use dev pc as callback/host (port forward?)
# sketchRequest: endpoint to receive from sketchServer, WS connections & start pubsub/topic requests
#   - get oauth2 tokens, pubsub updates
# create DB, move sketchAuth.py to DB
# store videos in DB

# alastairvods channel
ytTestChannel = 'UCmkonxPPduKnLNWvqhoHl_g'

# Needed from the YT API:

# - need an oauth2 token (refresh token > access token) to identify user
# - client id and secret to identify app

# Process:
# o user visits sketchServer to perform oauth2 with google / yt api
# o sketchServer passes refresh token to sketchRequest
# o sketchRequest uses refresh token to receive access token
# o call PlaylistItems with parts "snippet, contentDetails, status" to get all uploaded videos
# - call videos with parts "status" for all private videos (unlisted cant be scheduled)
#   - GET https://www.googleapis.com/youtube/v3/videos
#   - can only request 50 video ids at once (no pagination supported)
#   - get status.publishAt to see when the video will be published
# o subscribe to the channel for video updates so that we are notified when a video might be changing schedule / becoming private / unlisted
#   - update the video in the database when notified about it

# subscribes to every channel in database for notifications about new videos from youtube
async def youtubePrepareAllResubs():
    loop = asyncio.get_event_loop()
    async for channel in YoutubeChannel.all():
        leaseSeconds = channel.leaseSeconds
        timeAdded = channel.time
        if leaseSeconds and timeAdded:
            leaseSecondsDelta = datetime.timedelta(seconds=leaseSeconds)
            timeNow = datetime.datetime.now(datetime.timezone.utc)
            timeDifference = timeNow - timeAdded
            if timeDifference >= leaseSecondsDelta:
                # resub immediately
                loop.create_task(subscribeToYoutubeUploads(channel))
            else:
                timeDifference = leaseSecondsDelta - timeDifference
                loop.create_task(youtubeWaitForResub(timeDifference.total_seconds(), channel))

# waits to re-subscribe until subscription expiry
async def youtubeWaitForResub(seconds, youtubeChannel: YoutubeChannel):
    info(f'waiting {seconds} seconds to resub to {youtubeChannel.id}')
    await asyncio.sleep(seconds)
    await subscribeToYoutubeUploads(youtubeChannel)

# pubsub connection for notifications about uploads
async def subscribeToYoutubeUploads(ytChannel: YoutubeChannel):
    try:
        # if the channel has been deleted from the database this should cause some error
        await ytChannel.refresh_from_db()
        await ytChannel.fetch_related("youtubeAnnouncements")
        if not ytChannel.youtubeAnnouncements:
            # there are no yt announcements
            info(f'attempted subscription refresh for channel {ytChannel.id} with no associated announcements, so deleting')
            await ytChannel.delete()
            return 500
        baseCallbackURL = sketchAuth.devPublicCallbackURL if sketchShared.dev else sketchAuth.baseCallbackURL
        callbackURL = f'{baseCallbackURL}youtube/{ytChannel.id}'
        
        async with sketchServer.clientSession.post(f'https://pubsubhubbub.appspot.com/subscribe?hub.callback={callbackURL}&hub.topic=https://www.youtube.com/xml/feeds/videos.xml?channel_id={ytChannel.id}&hub.verify=async&hub.mode=subscribe') as resp:
            info(f'Subscription request to youtube channel {ytChannel.id} completed with status {resp.status}')
            return resp.status
    except:
        return 500
    


# gets all youtube videos from a channel that have been uploaded
# stores them in the database rn as a list in json format associated with a YoutubeChannel
async def gatherYoutubeVideos(ytChannel: YoutubeChannel):
    info(f'Beginning requests to collect all youtube videos for {ytChannel.id}')

    videoList = []

    # need user's "upload playlist" (search is limited to 500 videos and costs 100 query units vs 1 for list)
    # - the id of this playlist is the same as the channel's ID but the UC at the start is replaced with UU
    uploadPlaylist = ytChannel.id.replace('UC', 'UU', 1)

    params = {'part': 'snippet, contentDetails, status', 'maxResults': 50, 'playlistId': uploadPlaylist, 'key': sketchAuth.ytAppToken}

    # call PlaylistItems with parts "snippet, contentDetails, status" to get all uploaded videos
    # - use pagination to get info for all videos (max 50 per page)
    while True:
        async with sketchServer.clientSession.get('https://www.googleapis.com/youtube/v3/playlistItems', params=params) as resp:
            if resp.status != 200:
                return resp.status
            else:
                data = await resp.json()
                nextPage = data.get('nextPageToken')
                items = data.get('items')

                debug('Got response with next page: ' + str(nextPage))

                if items:
                    for video in data['items']:
                        videoList.append(video['contentDetails']['videoId'])
                else:
                    return resp.status
                
                if nextPage:
                    params['pageToken'] = nextPage
                else:
                    break
    
    # insert all collected videos into database so only new ones are announced from here
    ytChannel.announcedVideos = videoList
    await ytChannel.save(update_fields=['announcedVideos'])
    info(f'Finished requests for {ytChannel.id} videos. Inserted {len(videoList)} videos into database.')
    debug(str(videoList))
    return resp.status

# This is used when getting info from YT for displaying videos on the site, scheduling etc.
# To use this, I will need to change the JSONField to store dicts, or create a model for individual videos that store their id, titles, privacy status, etc. and create a one-to-many relation from the channel to the many videos
# creates / updates dictionary with video data from a list returned by youtube
# get status.privacyStatus to see if public, private, or unlisted (only care about private/unlisted)
# get snippet.title, snippet.thumbnails.(key).url (key is res value)
# contentDetails.videoPublishedAt useless, just says when uploaded until actually published
async def createVideoDictionary(items, vidDict={}):
    for video in items:
        videoID = video['contentDetails']['videoId']
        vidDict[videoID] = {
            'title': video['snippet']['title'] if video.get('snippet') else '',
            'privacyStatus': video['status']['privacyStatus'] if video.get('status') else '',
            'thumbnailUrl': video['snippet']['thumbnails']['high']['url'] if video.get('snippet') else ''
        }
    return vidDict

# TODO GET videos with parts "status" for schedule date of all private videos (unlisted cant be scheduled)
async def getScheduledDates(channelID, vidDict):
    pass

# TODO retrieve / determine current youtube API quota usage