import sketchShared
from sketchShared import debug, info, warn, error, critical
import base64, json
import sketchAuth, sketchServer

# TODO sketchServer: endpoints to receive YT oauth2 & pubsub
#   - use dev pc as callback/host (port forward?)
# TODO sketchRequest: endpoint to receive from sketchServer, WS connections & start pubsub/topic requests
#   - get oauth2 tokens, pubsub updates
# TODO create DB, move sketchAuth.py to DB
# TODO store videos in DB

# alastairvods channel
ytTestChannel = 'UCmkonxPPduKnLNWvqhoHl_g'

# Needed from the YT API:

# - need an oauth2 token (refresh token > access token) to identify user
# - client id and secret to identify app

# Process:
# o user visits sketchServer to perform oauth2 with google / yt api
# o sketchServer passes refresh token to sketchRequest
# o sketchRequest uses refresh token to receive access token
# - call PlaylistItems with parts "snippet, contentDetails, status" to get all uploaded videos
# - call videos with parts "status" for all private videos (unlisted cant be scheduled)
#   - GET https://www.googleapis.com/youtube/v3/videos
#   - can only request 50 video ids at once (no pagination supported)
#   - get status.publishAt to see when the video will be published
# - subscribe to the channel for video updates so that we are notified when a video might be changing schedule / becoming private / unlisted
#   - update the video in the database when notified about it

# https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps#exchange-authorization-code
# https://developers.google.com/identity/openid-connect/openid-connect#an-id-tokens-payload
async def getYoutubeTokens(code, userID):
    debug('Getting refresh token using code: ' + str(code) + ' for userID: ' + str(userID))

    async with sketchServer.session.post(
        "https://oauth2.googleapis.com/token" + 
        "?client_id=" + sketchAuth.ytClientID + 
        "&client_secret=" + sketchAuth.ytClientSecret + 
        "&code=" + code + 
        "&grant_type=authorization_code" + 
        "&redirect_uri=" + sketchAuth.callbackAddress + "youtube/callback"
    ) as resp:
        debug('Received response from YouTube for refresh token.')

        # json encoded access token returned
        data = await resp.json()
        debug('Response: ' + str(data))

        # TODO store these tokens in DB / associated with userID
        # TODO do something with the expires_in value returned
        if data and data.get('refresh_token') and data.get('access_token'):
            info('Received tokens for userID: ' + str(userID))

            sketchAuth.ytRefreshToken = data.get('refresh_token')
            sketchAuth.ytAccessToken = data.get('access_token')
            sketchAuth.ytId = await getUserIdFromEncodedGoogleIdToken(data.get('id_token'))

            result = """
                <div style="height: 100%; display: flex; justify-content: center; align-items: center">
                    <div>
                        <b>YouTube authorization successful!</b>
                    </div>
                </div>
            """
            await refreshYoutubeAccessToken('80085')
        else:
            error('Response error: either no refresh token or access token provided. (or no JSON at all)')
            
            result = """
                <div style="height: 100%; display: flex; justify-content: center; align-items: center">
                    <div>
                        <b>Error: Something went wrong with YouTube authorization.</b>
                        <br>Please try again, or contact alastairvox on discord.
                    </div>
                </div>
            """
        
        return result

# http://dev.fyicenter.com/1001053_Decode_Google_OpenID_Connect_id_token.html
async def getUserIdFromEncodedGoogleIdToken(id_token):
    debug('Decoding id token to retrieve users google id...')
    # the id token is 3 base64 encoded strings delimited by a period, the header (0), the json (1), and the signature (2)
    base64EncodedJSON = id_token.split('.')[1]
    # google does not properly pad the base64 strings, so we need to add padding. normally this means doing something with a multiple of 4 characters, but we can just add the max number of padding and let the base64 decoder strip any unnecesary padding (as it is set to do by default)
    decodedJSON = base64.b64decode(base64EncodedJSON + '==')
    decodedDict = json.loads(decodedJSON)
    return decodedDict['sub']


# https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps#offline
async def refreshYoutubeAccessToken(userID):
    # TODO code fallback for if refresh token becomes unusable (prompt re-authorization)
    #   - https://i.stack.imgur.com/Uf8KZ.png
    debug('Refreshing access token for userID: ' + str(userID))

    async with sketchServer.session.post(
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

# TODO GET PlaylistItems with parts "snippet, contentDetails, status" to get all uploaded videos
# https://developers.google.com/youtube/v3/docs/playlistItems/list
async def gatherYoutubeVideos(channelID):
    info('Beginning requests to collect all youtube videos for ' + str(channelID))

    userAuthenticated = True
    videoDictionary = {}

    # need user's "upload playlist" (search is limited to 500 videos and costs 100 query units vs 1 for list)
    # - the id of this playlist is the same as the channel's ID but the UC at the start is replaced with UU
    uploadPlaylist = channelID.replace('UC', 'UU', 1)

    if userAuthenticated:
        debug('User has previously authenticated: getting private and unlisted videos.')
        await refreshYoutubeAccessToken(':)')
        params = {'part': 'snippet, contentDetails, status', 'maxResults': 50, 'playlistId': uploadPlaylist, 'access_token': sketchAuth.ytAccessToken}
    else:
        params = {'part': 'snippet, contentDetails, status', 'maxResults': 50, 'playlistId': uploadPlaylist, 'key': sketchAuth.ytAppToken}

    # call PlaylistItems with parts "snippet, contentDetails, status" to get all uploaded videos
    # - use pagination to get info for all videos (max 50 per page)

    while True:
        async with sketchServer.session.get('https://www.googleapis.com/youtube/v3/playlistItems', params=params) as resp:
            if resp.status != 200:
                return resp.status
            else:
                data = await resp.json()
                nextPage = data.get('nextPageToken')
                items = data.get('items')

                debug('Got response with next page: ' + str(nextPage))

                if items:
                    videoDictionary = await createVideoDictionary(items)
                else:
                    return resp.status
                
                if nextPage:
                    params['pageToken'] = nextPage
                else:
                    break

    info('Finished requests for ' + str(channelID) + ' videos. Inserted ' + str(len(videoDictionary)) + ' videos into database.')
    debug(str(videoDictionary))
    return resp.status

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

# TODO pubsub connection
async def subscribeToYoutubeUploads(channelID):
    pass



# TODO retrieve / determine current youtube API quota usage