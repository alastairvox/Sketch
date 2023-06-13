import sketchShared
from sketchShared import debug, info, warn, error, critical
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
# - need user's "upload playlist" (search is limited to 500 videos and costs 100 query units vs 1 for list)
# - the id of this playlist is the same as the channel's ID but the UC at the start is replaced with UU
# - need an oauth2 token (refresh token > access token) to identify user
# - client id and secret to identify app

# Process:
# - user visits sketchServer to perform oauth2 with google / yt api
# - sketchServer passes refresh token to sketchRequest
# - sketchRequest uses refresh token to recieve access token
# - call PlaylistItems with parts "snippet, contentDetails, status" to get all uploaded videos
#   - GET https://www.googleapis.com/youtube/v3/playlistItems
#   - use pagination to get info for all videos (max 50 per page)
#   - get status.privacyStatus to see if public, private, or unlisted (only care about private/unlisted)
#   - get snippet.title, snippet.thumbnails.(key).url, and snippet.resourceId.videoId if private/unlisted
#   - will contentDetails.videoPublishedAt tell us when the video WILL be published or just upload date?
#     - if so we can avoid videos endpoint (double quota)
# - call videos with parts "status" for all private videos (unlisted cant be scheduled)
#   - GET https://www.googleapis.com/youtube/v3/videos
#   - can only request 50 video ids at once (no pagination supported)
#   - get status.publishAt to see when the video will be published

# TODO GET PlaylistItems with parts "snippet, contentDetails, status" to get all uploaded videos
async def gatherYoutubeVideos(channelID):
    pass

# TODO GET videos with parts "status" for schedule date of all private videos (unlisted cant be scheduled)
async def getScheduledDates(channelID, videoList):
    pass

# TODO pubsub connection
async def subscribeToYoutubeUploads(channelID):
    pass

async def getYoutubeRefreshToken(code, userID):
    info('Getting refresh token using code: ' + str(code) + ' for userID: ' + str(userID))

    async with sketchServer.session.post("https://oauth2.googleapis.com/token" + 
    "?client_id=" + sketchAuth.ytClientID + 
    "&client_secret=" + sketchAuth.ytClientSecret + 
    "&code=" + code + 
    "&grant_type=authorization_code" + 
    "&redirect_uri=" + sketchAuth.callbackAddress + "youtube/callback") as resp:
        debug('Received response from YouTube for refresh token.')

        # json encoded access token returned
        info = await resp.json()
        debug('Response: ' + str(info))

        # TODO store these tokens in DB / associated with userID
        # TODO do something with the expires_in value returned
        if info and info.get('refresh_token') and info.get('access_token'):
            sketchAuth.ytRefreshToken = info.get('refresh_token')
            sketchAuth.ytAccessToken = info.get('access_token')

            result = """<div style="height: 100%; display: flex; justify-content: center; align-items: center">
                <div>
                    <b>YouTube authorization successful!</b>
                </div>
            </div>"""
        else:
            debug('Response error: either no refresh token or access token provided. (or no JSON at all)')
            
            result = """<div style="height: 100%; display: flex; justify-content: center; align-items: center">
                <div>
                    <b>Error: Something went wrong with YouTube authorization.</b>
                    <br>Please try again, or contact alastairvox on discord.
                </div>
            </div>"""
        
        return result

async def refreshYoutubeAccessToken(userID):
    # TODO code refresh youtube tokens
    # TODO code fallback for if refresh token becomes unusable (prompt re-authorization)
    #   - https://i.stack.imgur.com/Uf8KZ.png
    pass


# TODO retrieve / determine current youtube API quota usage