import sketchShared
from sketchShared import debug, info, warn, error, critical
from typing import Any, Optional, Literal, List, Union
import discord, asyncio, traceback, dateutil.parser, pytz, datetime, re
from discord import app_commands
from discord.ext import commands
import sketchAuth
from sketchModels import *

# MARK: SETUP -------------------------------------------------------------------------------------------------------------

# gets rid of annoying warning about not having the voice client :)
discord.VoiceClient.warn_nacl = False

class SketchBot(commands.Bot):
    def __init__(self):
        # subscribe to intents so that you can recieve information
        intents = discord.Intents.all()
        # passing an empty list as the command prefix disables text commands :)
        super().__init__(command_prefix=[], intents=intents, case_insensitive=True, status='a friend', allowed_mentions=discord.AllowedMentions.all())

    async def setup_hook(self) -> None:
        # lists here are faster than a set because they will need to be fully iterated when removing a role, and are generally small (<25) so "if message in list" will be fast enough
        # {'channelId': ['messageId','messageId','messageId','messageId']}
        self.roleMessageDict: dict[int, list[discord.Message]] = {}
        # get any needed data for servers from database here?
        pass

    async def on_ready(self):
        info(f'Connected as {bot.user} (ID: {self.user.id}) to "' + '", "'.join(map(str, bot.guilds)) + '"')
        # get all the guilds Sketch is connected to and check if they all have entries in the config file, if not then create a default one
        await configNewGuilds()
        # await syncAllCommands()

bot = SketchBot()

successColour = discord.Colour.from_str('#eac467')
failColour = discord.Colour.from_str('#2c3843')
defaultColour = discord.Colour.from_str('#a92835')
defaultColourHex = '#a92835'

# starts the bot when called
async def summon():
    info("Summoning...")
    await bot.start(sketchAuth.discordBotToken, reconnect=True)

# MARK: FUNCTIONS ---------------------------------------------------------------------------------------------------------

# test command
async def test() -> str:
    debug("Test called!")
    try:
        await bot.get_channel(977628532282888202).send("test from web")
    except Exception as e:
        warn("Error: " + str(e))
        return "Error: " + str(e)
    return "Success!"

# sets database defaults for guilds that sketch is in and updates the owners and names of the guilds
async def configNewGuilds():
    debug('In guilds: ' + str(bot.guilds))
    for guild in bot.guilds:
        # add guild to database, update name and owner id
        await DiscordGuild.update_or_create(id=guild.id, defaults={'name': guild.name, 'owner': guild.owner_id})
        # add owner to database, update name
        await DiscordUser.update_or_create(id=guild.owner_id, defaults={'name': guild.owner.global_name, 'username': guild.owner.name})
        # we dont add the guild the user owns to the list of authorized guilds, because it could change at any time and we don't have a way to separate manually authorized users from unauthorized ones

# tells discord what commands my bot knows
async def syncAllCommandsToTestServer() -> None:
    warn('MANUALLY SYNCING ALL COMMANDS TO TEST SERVER')
    testServer = discord.Object(sketchAuth.discordTestServerID)
    bot.tree.copy_global_to(guild=testServer)
    await bot.tree.sync(guild=testServer)

async def syncAllCommands() -> None:
    warn('MANUALLY SYNCING ALL GLOBAL COMMANDS AND THEN COMMANDS FOR ALL CONNECTED GUILDS')
    await bot.tree.sync()
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass

# generic test to see if interaction user is ME
def isOwner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == sketchAuth.discordOwner

# TODO removeAnnouncement
async def removeAnnouncement(dbStream: TwitchAnnouncement):
    await dbStream.fetch_related('guild')
    offlineURL = dbStream.offlineImageURL
    
    timeZone = dbStream.guild.timeZone
    deleteAnnouncements = dbStream.guild.deleteOldAnnouncements
    # if this is not 0 (python treats a 0 value int as False) then theres a delay
    spamProtectionAnnounceDelay = dbStream.guild.spamProtectionAnnounceDelay

    # get discord objects
    guild = bot.get_guild(dbStream.guild.id)
    announceChannel = guild.get_channel(dbStream.channelID)

    # try except so that it can skip all this if announcement message cant be found
    try:
        # get announcement message
        announcement = await announceChannel.fetch_message(dbStream.messageID)

        if spamProtectionAnnounceDelay:
            utcTZ = pytz.timezone('UTC')
            # if the stream hasn't had its end time stored yet ('ended' key does not exist)
            if not dbStream.ended:
                dbStream.ended = datetime.datetime.now(utcTZ)
                await dbStream.save(update_fields=['ended'])
                info(f'Delaying removal due to spamProtectionAnnounceDelay on {guild.name}.')
                return
            # else if the difference between now and the time the stream actually ended is less than the double ping delay time (badinternet) (spamProtectionAnnounceDelay)
            elif (datetime.datetime.now(utcTZ) - dbStream.ended) < datetime.timedelta(minutes=spamProtectionAnnounceDelay):
                return
            # otherwise, continue and delete/edit the announcement

        if deleteAnnouncements:
            info(f'Removing announcement for {guild.name}.')
            await announcement.delete()
        else:
            userMentions = announcement.mentions
            roleMentions = announcement.role_mentions
            
            newContent = ''
            if '@everyone' in announcement.content:
                newContent += '@everyone '
            if '@here' in announcement.content:
                newContent += '@here '
            for role in roleMentions:
                newContent += role.mention + ' '
            for user in userMentions:
                newContent += user.mention + ' '
            
            newContent += f'{dbStream.streamName} is no longer live.'
            announcement.content = newContent

            # get date/convert date from UTC
            timeStarted = announcement.embeds[0].timestamp
            newTZ = pytz.timezone(timeZone)
            newTimeStarted = timeStarted.replace(tzinfo=pytz.utc).astimezone(newTZ)
            timeStarted = newTZ.normalize(newTimeStarted) # .normalize might be unnecessary
            if not dbStream.ended:
                timeEnded = datetime.datetime.now(newTZ).strftime("%#I:%M %p (%Z)")
                endedFooter = datetime.datetime.now(newTZ).strftime("%b %#d at %#I:%M %p (%Z)")
                duration = datetime.datetime.now(newTZ) - timeStarted
            else:
                timeEnded = dbStream.ended
                newTimeEnded = timeEnded.replace(tzinfo=pytz.utc).astimezone(newTZ)
                timeEnded = newTZ.normalize(newTimeEnded).strftime("%#I:%M %p (%Z)") # .normalize might be unnecessary
                endedFooter = newTZ.normalize(newTimeEnded).strftime("%b %#d at %#I:%M %p (%Z)")
                duration = dbStream.ended - timeStarted

            # creation of embed
            hours, remainder = divmod(duration.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration = '{:2}h {:2}m {:2}s'.format(int(hours), int(minutes), int(seconds))
            announcement.embeds[0].insert_field_at(index=1,name='Ended',value=timeEnded,inline=True)
            announcement.embeds[0].insert_field_at(index=2,name='Duration',value=duration,inline=True)
            announcement.embeds[0].set_field_at(index=3,name='Played',value=announcement.embeds[0].fields[3].value)
            announcement.embeds[0].set_footer(text='Ended    •  ' + endedFooter + '\nStarted')
            if offlineURL:
                announcement.embeds[0].set_image(url=offlineURL.replace('-1920x1080', ''))
            else:
                announcement.embeds[0].set_image(url=offlineURL)

            info(f'Editing announcement for {dbStream.streamName} to reflect offline state.')
            await announcement.edit(content=announcement.content,embed=announcement.embeds[0])

    except discord.errors.NotFound:
        error('Announcement no longer exists (deleted after announcing).')
        if spamProtectionAnnounceDelay:
            utcTZ = pytz.timezone('UTC')       
            # if the stream hasn't had its end time stored yet ('ended' key does not exist)
            if not dbStream.ended:
                dbStream.ended = datetime.datetime.now(utcTZ)
                await dbStream.save(update_fields=['ended'])
                info(f'Delaying removal due to spamProtectionAnnounceDelay on {guild.name}.')
                return
            # else if the difference between now and the time the stream actually ended is less than the double ping delay time (badinternet) (spamProtectionAnnounceDelay)
            elif (datetime.datetime.now(utcTZ) - dbStream.ended) < datetime.timedelta(minutes=spamProtectionAnnounceDelay):
                return
            # otherwise, continue and delete/edit the announcement
        info(f'Removing stored reference to deleted announcement for {dbStream.streamName}.')

    # reset the announcement holder
    dbStream.messageID = None
    await dbStream.save(update_fields=['messageID'])
    if dbStream.ended:
        dbStream.ended = None
        await dbStream.save(update_fields=['ended'])

# TODO makeAnnouncement
async def makeAnnouncement(dbStream: TwitchAnnouncement, twitchioStream, game):
    # no more streamRole, just send the announce message
    # no more botChannel (unless i want a special override). old message: \nIf you don't want these notifications, go to " + botChannel.mention + " and type ``" + prefix + "notify``.
    await dbStream.refresh_from_db()
    await dbStream.fetch_related('guild')
    timeZone = dbStream.guild.timeZone
    # no more prefix, only app commands
    # profileURL is in the dbStream at profileImageURL
    profileURL = dbStream.profileImageURL
    # no more overrideRole

    # get objects from discord api
    guild = bot.get_guild(dbStream.guild.id)

    announceChannel = guild.get_channel(dbStream.channelID)

    # get date/convert date from UTC
    date = twitchioStream.started_at
    newTZ = pytz.timezone(timeZone)
    newDate = date.replace(tzinfo=pytz.utc).astimezone(newTZ)
    date = newTZ.normalize(newDate) # .normalize might be unnecessary
    dateString = date.strftime("%#I:%M %p (%Z)")

    # text content
    message = dbStream.announcementText

    # embed content
    embed = discord.Embed()
    embed.title = 'https://twitch.tv/' + twitchioStream.user.name
    embed.url = embed.title
    embed.colour = 6570404
    embed.timestamp = date
    embed.set_footer(text='Started')
    embed.set_image(url=twitchioStream.thumbnail.base_url.replace('-{width}x{height}', ''))
    embed.set_author(name=twitchioStream.title, url='https://twitch.tv/' + twitchioStream.user.name, icon_url=profileURL)
    debug(profileURL)
    debug(embed.author)
    if game and game.box_art:
        embed.set_thumbnail(url=game.box_art.base_url.replace('-{width}x{height}', '').replace('/ttv-boxart/./', '/ttv-boxart/'))
    else:
        embed.set_thumbnail(url='https://static-cdn.jtvnw.net/ttv-static/404_boxart.jpg')
    embed.add_field(name='Started',value=dateString, inline=True)
    embed.add_field(name='Playing',value=game.name, inline=True)

    sent = await announceChannel.send(message, embed=embed)
    debug(f'Sent message to {str(announceChannel.guild)}: {sent}')
    dbStream.messageID = sent.id
    await dbStream.save(update_fields=['messageID'])

# takes a space delimited list of discord guild ids and turns them into generic discord objects
class GuildListTransformer(app_commands.Transformer):
    async def transform(self, interaction: discord.Interaction, value: str) -> List[discord.Object]:
        guildList = []
        stringList = value.split()
        for guild in stringList:
            guildList.append(discord.Object(guild))
        return guildList

# custom embed that has thumbnails and footer and default colour
class BaseEmbed(discord.Embed):
    def __init__(self, *args, colour=defaultColour, footer: Optional[str] = None, thumbnail: Optional[discord.Asset] = None, **kwargs):
        super().__init__(*args, colour=colour, **kwargs)
        if not footer:
            self.set_footer(text="I'm on a mission...", icon_url=bot.user.display_avatar.url)
        else:
            self.set_footer(text=footer, icon_url=bot.user.display_avatar.url)
        if thumbnail:
            self.set_thumbnail(url=thumbnail.url)

# an embed with a green sidebar, and defaults to saying success in title and great work in footer
class SuccessEmbed(BaseEmbed):
    def __init__(self, *args, title="Success!", colour=successColour, footer: Optional[str] = 'Great work!', **kwargs):
        super().__init__(*args, title=title, colour=colour, footer=footer, **kwargs)

# an embed with a black-ish sidebar, and defaults to saying cancelled in title and well get em next time in footer
class CancelEmbed(BaseEmbed):
    def __init__(self, *args, title="Cancelled!", colour=failColour, footer: Optional[str] = "We'll get 'em next time.", **kwargs):
        super().__init__(*args, title=title, colour=colour, footer=footer, **kwargs)

# a base view for responses that will disable buttons on timeout and handle errors in responses
class BaseView(discord.ui.View):
    async def on_timeout(self):
        debug('View timed out: ' + str(self))
        # if we have passed a message to this view, because it has buttons
        if self.message:
            debug('view timed out for message: ' + str(self.message))
            for item in self.children:
                item.disabled = True
            oldEmbed = self.message.embeds[0]
            newEmbed = oldEmbed.set_footer(text="You ignored me... 😭 I timed out! Try again!", icon_url=oldEmbed.footer.icon_url)
            try:
                await self.message.edit(embed=newEmbed, view=self)
                await self.message.delete(delay=8)
            except discord.errors.NotFound:
                debug('Tried deleting timed-out message that cant be found. Ignoring...')
        self.stop()

    # async def on_error(self, interaction: discord.Interaction, err: Exception):
    #     await on_app_command_error(interaction, err)

class AddRoleView(BaseView):
    def __init__(self, *args, roleMessage, deleteOnCancel=False, timeout=180, **kwargs):
        super().__init__(*args, timeout=timeout, **kwargs)
        debug('storing role message in view' + str(roleMessage))
        self.roleMessage=roleMessage
        self.deleteOnCancel=deleteOnCancel

        # get list of roles on server
        self.rolePages = []
        allRoles = list(roleMessage.guild.roles)
        if allRoles:
            # remove "@everyone"
            allRoles.pop(0)
        chunkSize = 25
        while allRoles:
            chunk, allRoles = allRoles[:chunkSize], allRoles[chunkSize:]
            self.rolePages.append(chunk)
        debug('Created chunked list of roles: ' + str(self.rolePages))

        self.currentPage = 0
        self.currentRoleSelect = ChunkedRoleSelect(self.rolePages[0])
        self.add_item(self.currentRoleSelect)

        # if theres 0 or 1 pages in the list, disable forward navigation
        if len(self.rolePages) <= 1:
            self.nextPage.disabled=True

    @discord.ui.button(label='⬅ Previous', style=discord.ButtonStyle.blurple, row=1, disabled=True)
    async def previousPage(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        self.currentPage = self.currentPage - 1

        self.remove_item(self.currentRoleSelect)
        # the button starts disabled and disables itself any time page goes to 0 so this can never be called at 0
        self.currentRoleSelect = ChunkedRoleSelect(self.rolePages[self.currentPage])
        self.add_item(self.currentRoleSelect)

        if self.currentPage <= 0:
            self.previousPage.disabled = True
        else:
            self.previousPage.disabled = False

        if (self.currentPage + 1) >= len(self.rolePages):
            self.nextPage.disabled = True
        else:
            self.nextPage.disabled = False

        originalResponse = await interaction.original_response()
        embed = await self.getEmbed(originalResponse.embeds[0])

        self.message = await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger, row=1)
    async def cancelRoleSelect(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

        embed = CancelEmbed()
        cancelMessage = await interaction.followup.send(embed=embed, ephemeral=True)
        await cancelMessage.delete(delay=3)

        if self.deleteOnCancel:
            await self.roleMessage.delete()

    @discord.ui.button(label='Next ➡', style=discord.ButtonStyle.blurple, row=1)
    async def nextPage(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        self.currentPage = self.currentPage + 1

        self.remove_item(self.currentRoleSelect)
        # starts disabled if not enough pages left and disables when not enough pages left so can never exceed index
        self.currentRoleSelect = ChunkedRoleSelect(self.rolePages[self.currentPage])
        self.add_item(self.currentRoleSelect)

        if self.currentPage <= 0:
            self.previousPage.disabled=True
        else:
            self.previousPage.disabled=False

        if (self.currentPage + 1) >= len(self.rolePages):
            self.nextPage.disabled=True
        else:
            self.nextPage.disabled=False

        originalResponse = await interaction.original_response()
        embed = await self.getEmbed(originalResponse.embeds[0])

        self.message = await interaction.edit_original_response(embed=embed, view=self)

    async def getEmbed(self, prevEmbed: discord.Embed = None):
        if prevEmbed:
            embed=prevEmbed
            if embed.fields:
                embed.set_field_at(
                    -1,
                    name=embed.fields[-1].name,
                    value='Page ' + str(self.currentPage+1) + '/' + str(len(self.rolePages))
                )
            else:
                embed.add_field(
                    name='Current Page',
                    value='Page ' + str(self.currentPage+1) + '/' + str(len(self.rolePages))
                )
        return embed

    async def on_timeout(self):
        debug('role view timed out for rolemessage: ' + str(self.roleMessage))
        await super().on_timeout()
        if self.deleteOnCancel:
            try:
                await self.roleMessage.delete(delay=8)
            except discord.errors.NotFound:
                debug('Tried deleting role message on cancel that couldnt be found. Ignoring...')

class ChunkedRoleSelect(discord.ui.Select):
    def __init__(self, options=[]):
        self.originalRoles = options

        if options:
            # use list comprehension to turn the passed list of roles into a list of SelectOptions
            self.optionsRoles = [discord.SelectOption(label=role.name, value=role.id) for role in options]
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the three options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(placeholder='Select a role to add...', min_values=1, max_values=1, options=self.optionsRoles)

    async def callback(self, interaction: discord.Interaction):
        # Use the interaction object to send a response message containing
        # the user's favourite colour or choice. The self object refers to the
        # Select object, and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        await interaction.response.defer()

        selectedRole = None
        for role in self.originalRoles:
            if role.id == int(self.values[0]):
                selectedRole = role
                self.view.selectedRole = selectedRole
                break
        
        if not selectedRole:
            raise Exception('idk some stuff wonky that role got messed up')
        else:
            originalResponse = await interaction.original_response()
            embed = originalResponse.embeds[0]
            embed.remove_field(-1)
            embed.description='# ' + self.view.selectedRole.name + '\n### Please react to ***self-role message*** (' + self.view.roleMessage.jump_url + ') with the emoji you want for this button!\n*Note: I can only use default emoji or this servers emoji!*\n\nClick "Continue Without Emoji" for a text-only button.'

            self.view.clear_items()
            waitingButton = WaitingEmojiButton()
            self.view.add_item(waitingButton)
            self.view.message = await interaction.edit_original_response(embed=embed, view=self.view)
            await waitingButton.waitForReactionOnRoleMessage(interaction)

class WaitingEmojiButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Continue Without Emoji', emoji='❌')
        self.waiting = True

    async def waitForReactionOnRoleMessage(self, interaction: discord.Interaction):
        def check(reaction: discord.RawReactionActionEvent):
            return reaction.event_type == 'REACTION_ADD' and reaction.message_id == self.view.roleMessage.id and reaction.user_id == interaction.user.id
        
        goodEmoji = None
        while not goodEmoji:
            try:
                reaction = await bot.wait_for('raw_reaction_add', timeout=178.0, check=check)
            except asyncio.TimeoutError:
                break
            else:
                # if we stopped waiting (cause they said no emoji) then do nothing
                if not self.waiting:
                    debug('got author reaction on role message but wasnt waiting, so ignoring')
                    break
                debug('got a reaction from author on role message ' + str(reaction))
                if reaction.emoji.is_custom_emoji():
                    # check if the emoji is valid
                    getEmojiResult = bot.get_emoji(reaction.emoji.id)
                    if not getEmojiResult:
                        try:
                            getEmojiResult = await interaction.guild.fetch_emoji(reaction.emoji.id)
                            goodEmoji = getEmojiResult
                        except:
                            error('error on trying to fetch custom emoji from reaction while waiting: ' + str(reaction))
                            oopsEmbed = CancelEmbed(title='I cant use that emoji! Please use a default emoji or one uploaded to this server.')
                            cancelMessage = await interaction.followup.send(embed=oopsEmbed, ephemeral=True)
                            await cancelMessage.delete(delay=3)
                            await self.view.roleMessage.remove_reaction(reaction.emoji, interaction.user)
                    else:
                        goodEmoji = getEmojiResult
                else:
                    goodEmoji = reaction.emoji.name
        if goodEmoji:
            debug('GOT A GOOD EMOJI YEEHAW ' + str(goodEmoji))
            await self.view.roleMessage.remove_reaction(goodEmoji, interaction.user)
            self.view.goodEmoji = goodEmoji
            await self.finalizeRoleCreation(interaction)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        self.waiting = False
        await self.finalizeRoleCreation(interaction)

    async def finalizeRoleCreation(self, interaction: discord.Interaction):
        originalResponse = await interaction.original_response()
        embed = originalResponse.embeds[0]
        if hasattr(self.view, 'goodEmoji'):
            embed.description = str(self.view.goodEmoji) + ': ' + self.view.selectedRole.name + '\n# ' + str(self.view.goodEmoji) + ' ' + self.view.selectedRole.name
        else:
            embed.description = self.view.selectedRole.name + '\n# ' + self.view.selectedRole.name
        embed.description = embed.description + '\n### Great choice! If you want, you can:\n- Edit the buttons label (Default: `' + self.view.selectedRole.name + '`)\n- Edit the roles description in the self-role message (Default: `' + self.view.selectedRole.name + '`)\n- Edit the buttons colour (Default: `grey`)\n- Cancel adding this role button\n- Finish and add the role button!'
        self.view.clear_items()
        self.view.add_item(EditRoleLabelBtn())
        self.view.add_item(EditRoleDescriptionBtn())
        self.view.add_item(EditRoleColourSelect())
        self.view.add_item(CancelRoleBtn())
        self.view.add_item(ConfirmRoleBtn())
        self.view.message = await interaction.edit_original_response(embed=embed, view=self.view)

class EditRoleLabelBtn(discord.ui.Button):
    def __init__(self, style=discord.ButtonStyle.secondary):

        super().__init__(label='Edit Label', emoji='🏷', style=style)

    async def callback(self, interaction: discord.Interaction):
        debug('reached callback for EditRoleLabel button, sending modal')
        await interaction.response.send_modal(EditRoleModal(self.view, interaction, type='label'))

class EditRoleDescriptionBtn(discord.ui.Button):
    def __init__(self, style=discord.ButtonStyle.secondary):
        super().__init__(label='Edit Description', emoji='📝', style=style)

    async def callback(self, interaction: discord.Interaction):
        debug('reached callback for EditRoleDescription button, sending modal')
        await interaction.response.send_modal(EditRoleModal(self.view, interaction, type='description'))

class EditRoleModal(discord.ui.Modal):
    def __init__(self, originalView: discord.ui.View=None, originalInteraction: discord.Interaction=None, type: str = ''):
        self.originalView = originalView
        self.originalInteraction = originalInteraction
        self.type = type
        if type == 'description':
            super().__init__(title='Edit Role Button Description', timeout=178)
            self.newDescription = discord.ui.TextInput(label='New Description', default=originalView.selectedRole.name, placeholder='Enter new description...', required=True, max_length=130)
            self.add_item(self.newDescription)
        else:
            super().__init__(title='Edit Role Button Label', timeout=178)
            self.newLabel = discord.ui.TextInput(label='New Label', default=originalView.selectedRole.name, placeholder='Enter new label...', required=True, max_length=80)
            self.add_item(self.newLabel)

    async def on_submit(self, interaction: discord.Interaction):
        if self.type == 'description':
            self.originalView.newDescription = str(self.newDescription)
            newValue = str(self.newDescription)
        else:
            self.originalView.newLabel = str(self.newLabel)
            newValue = str(self.newLabel)

        debug('editrolemodal submitted submitted value is: ' + newValue)

        embed = SuccessEmbed(title='Button ' + self.type + ' updated!', description='New button ' + self.type + ': `' + newValue + '`')
        await interaction.response.send_message(embed=embed, ephemeral=True)
        successMessage = await interaction.original_response()
        await successMessage.delete(delay=3)

        embed: discord.Embed = self.originalView.message.embeds[0]
        
        if self.type == 'description':
            labelStr = self.originalView.newLabel if hasattr(self.originalView, 'newLabel') else self.originalView.selectedRole.name
            descriptionStr = newValue
        else:
            labelStr = newValue
            descriptionStr = self.originalView.newDescription if hasattr(self.originalView, 'newDescription') else self.originalView.selectedRole.name

        if hasattr(self.originalView, 'goodEmoji'):
            emojiStr = str(self.originalView.goodEmoji)
            descriptionStr = self.originalView.newDescription if hasattr(self.originalView, 'newDescription') else self.originalView.selectedRole.name
            embedDescriptionPrefix = emojiStr + ': ' + descriptionStr + '\n# ' + emojiStr + ' ' + labelStr
        else:
            embedDescriptionPrefix = ((labelStr + ': ') if hasattr(self.originalView, 'newLabel') else (self.originalView.selectedRole.name + ': ')) + descriptionStr + '\n# ' + labelStr
        embed.description = embedDescriptionPrefix + '\n### ' + embed.description.split('### ',1)[1]

        self.originalView.message = await self.originalInteraction.edit_original_response(embed=embed)

class EditRoleColourSelect(discord.ui.Select):
    def __init__(self, placeholder='Change button colour...'):
        options = [
            discord.SelectOption(label='blurple'),
            discord.SelectOption(label='grey'),
            discord.SelectOption(label='green'),
            discord.SelectOption(label='red'),
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        debug('reached callback for EditRoleColorSelect, recreating view')
        await interaction.response.defer()

        match self.values[0]:
            case "blurple":
                style = discord.ButtonStyle.blurple
            case "grey":
                style = discord.ButtonStyle.secondary
            case "green":
                style = discord.ButtonStyle.success
            case "red":
                style = discord.ButtonStyle.danger
            case _:
                style = discord.ButtonStyle.secondary

        self.view.newStyle = style

        self.view.clear_items()
        self.view.add_item(EditRoleLabelBtn(style=style))
        self.view.add_item(EditRoleDescriptionBtn(style=style))
        self.view.add_item(EditRoleColourSelect(placeholder=self.values[0]))
        self.view.add_item(CancelRoleBtn())
        self.view.add_item(ConfirmRoleBtn())
        self.view.message = await interaction.edit_original_response(view=self.view)

        embed = SuccessEmbed(title='Button colour updated!', description='New button colour: `' + self.values[0] + '`')
        successMessage = await interaction.followup.send(embed=embed, ephemeral=True)
        await successMessage.delete(delay=3)

class CancelRoleBtn(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Cancel', style=discord.ButtonStyle.danger, row=2)
        
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.delete_original_response()

        embed = CancelEmbed()
        cancelMessage = await interaction.followup.send(embed=embed, ephemeral=True)
        await cancelMessage.delete(delay=3)

        if self.view.deleteOnCancel:
            await self.view.roleMessage.delete()

class ConfirmRoleBtn(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Finish', style=discord.ButtonStyle.success, row=2)
        
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        newLabel = self.view.newLabel if hasattr(self.view, 'newLabel') else self.view.selectedRole.name
        goodEmoji = self.view.goodEmoji if hasattr(self.view, 'goodEmoji') else None
        newStyle = self.view.newStyle if hasattr(self.view, 'newStyle') else discord.ButtonStyle.secondary
        newDescription = self.view.newDescription if hasattr(self.view, 'newDescription') else self.view.selectedRole.name

        roleMessage: discord.Message = self.view.roleMessage
        newView: discord.ui.View = discord.ui.View.from_message(roleMessage)

        numDuplicates = 0
        for button in newView.children:
            if str(self.view.selectedRole.id) in button.custom_id:
                numDuplicates = numDuplicates + 1

        newButton = discord.ui.Button(
            custom_id='r:' + str(numDuplicates) + ':' + str(self.view.selectedRole.id),
            label=newLabel,
            emoji=goodEmoji,
            style=newStyle
        )

        newView.add_item(newButton)

        newEmbed: discord.Embed = roleMessage.embeds[0]
        newLines = '\n\n' if len(roleMessage.components) <= 0 else '\n'
        # im sorry
        newEmbed.description = newEmbed.description + newLines + ((str(goodEmoji) + ': ') if goodEmoji else ((newLabel + ': ') if newLabel != newDescription else newLabel)) + (newDescription if newLabel != newDescription else ('' if not goodEmoji else newDescription))
        
        # if this process was started by a "new role message" command then add the message to the cache 
        if self.view.deleteOnCancel:
            if interaction.channel_id in bot.roleMessageDict:
                bot.roleMessageDict[interaction.channel_id].append(roleMessage)
            else:
                bot.roleMessageDict[interaction.channel_id] = [roleMessage]

        await roleMessage.edit(embed=newEmbed, view=newView)

        await interaction.delete_original_response()

        embed = SuccessEmbed(title='Role button added!')
        successMessage = await interaction.followup.send(embed=embed, ephemeral=True)
        await successMessage.delete(delay=3)

        self.view.stop()

class SelectRoleMessageView(BaseView):
    def __init__(self, *args, channel: Optional[Union[discord.abc.GuildChannel, discord.abc.PrivateChannel, discord.Thread]] = None, timeout=180, deletingButton = False, **kwargs):
        super().__init__(*args, timeout=timeout, **kwargs)

        # get list of messages in channel
        self.messagePages = []
        chunkSize = 25
        allChannelRoleMessages = bot.roleMessageDict.get(channel.id)
        # convert all messages into a PartialMessage
        while allChannelRoleMessages:
            chunk, allChannelRoleMessages = allChannelRoleMessages[:chunkSize], allChannelRoleMessages[chunkSize:]
            self.messagePages.append(chunk)
        debug('Created chunked list of messages: ' + str(self.messagePages))

        self.currentPage = 0
        if self.messagePages:
            self.currentMessageSelect = ChunkedMessageSelect(self.messagePages[0], deletingButton)
        else:
            self.currentMessageSelect = ChunkedMessageSelect(self.messagePages, deletingButton)
        self.add_item(self.currentMessageSelect)

        # if theres 0 or 1 pages in the list, disable forward navigation
        if len(self.messagePages) <= 1:
            self.nextPage.disabled=True

    @discord.ui.button(label='⬅ Previous', style=discord.ButtonStyle.blurple, row=1, disabled=True)
    async def previousPage(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        self.currentPage = self.currentPage - 1

        self.remove_item(self.currentMessageSelect)
        # the button starts disabled and disables itself any time page goes to 0 so this can never be called at 0
        self.currentMessageSelect = ChunkedMessageSelect(self.messagePages[self.currentPage])
        self.add_item(self.currentMessageSelect)

        if self.currentPage <= 0:
            self.previousPage.disabled=True
        else:
            self.previousPage.disabled=False

        if (self.currentPage + 1) >= len(self.messagePages):
            self.nextPage.disabled=True
        else:
            self.nextPage.disabled=False

        originalResponse = await interaction.original_response()
        embed = await self.getEmbed(originalResponse.embeds[0])

        self.message = await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger, row=1)
    async def cancelMessageSelect(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

        embed = CancelEmbed()
        cancelMessage = await interaction.followup.send(embed=embed, ephemeral=True)
        await cancelMessage.delete(delay=3)

    @discord.ui.button(label='Next ➡', style=discord.ButtonStyle.blurple, row=1)
    async def nextPage(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        self.currentPage = self.currentPage + 1

        self.remove_item(self.currentMessageSelect)
        # starts disabled if not enough pages left and disables when not enough pages left so can never exceed index
        self.currentMessageSelect = ChunkedMessageSelect(self.messagePages[self.currentPage])
        self.add_item(self.currentMessageSelect)

        if self.currentPage <= 0:
            self.previousPage.disabled=True
        else:
            self.previousPage.disabled=False

        if (self.currentPage + 1) >= len(self.messagePages):
            self.nextPage.disabled=True
        else:
            self.nextPage.disabled=False

        originalResponse = await interaction.original_response()
        embed = await self.getEmbed(originalResponse.embeds[0])

        self.message = await interaction.edit_original_response(embed=embed, view=self)

    async def getEmbed(self, prevEmbed: discord.Embed = None):
        if prevEmbed:
            embed=prevEmbed
            if embed.fields:
                embed.set_field_at(
                    -1,
                    name=embed.fields[-1].name,
                    value='Page ' + str(self.currentPage+1) + '/' + str(len(self.messagePages))
                )
            else:
                embed.add_field(
                    name='Current Page',
                    value='Page ' + str(self.currentPage+1) + '/' + str(len(self.messagePages))
                )
        return embed

    async def on_timeout(self):
        debug('select message view timed out')
        await super().on_timeout()

class ChunkedMessageSelect(discord.ui.Select):
    def __init__(self, options: List[discord.Message]=[], deletingButton=False):
        self.originalMessages = options
        self.deletingButton = deletingButton

        if options:
            # use list comprehension to turn the passed list of roles into a list of SelectOptions
            self.optionsMessage = [discord.SelectOption(label=message.embeds[0].title[:100], value=str(message.id), description=message.embeds[0].description[:100]) for message in options]
            super().__init__(placeholder='Select a role message...', min_values=1, max_values=1, options=self.optionsMessage)
        else:
            super().__init__(placeholder='No role messages in this channel!', min_values=1, max_values=1, disabled=True, options=[discord.SelectOption(label='')])

    async def callback(self, interaction: discord.Interaction):
        # Use the interaction object to send a response message containing
        # the user's favourite colour or choice. The self object refers to the
        # Select object, and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        await interaction.response.defer()

        selectedMessage = None
        for message in self.originalMessages:
            if message.id == int(self.values[0]):
                selectedMessage = await message.fetch()
                self.view.roleMessage = selectedMessage
                break
        
        if not selectedMessage:
            raise Exception('idk some stuff wonky that role message got messed up')
        else:
            if not self.deletingButton:
                self.view.stop()
                view = AddRoleView(roleMessage=selectedMessage)
                embed = await view.getEmbed(BaseEmbed(
                    title="Let's add a role!",
                    description="""Choose a role to add to the self-assignable role message.\n\nDiscord only lets me have 25 options in a list... so use the buttons to navigate pages if you have more roles than that!\n\n(also tell Discord that is insane?? ((they won't let me in to talk after they caught me in the dumpster)))""",
                    thumbnail = interaction.guild.icon
                ))
                view.message = await interaction.edit_original_response(embed=embed, view=view)
            else:
                originalResponse = await interaction.original_response()
                embed = originalResponse.embeds[0]
                embed.remove_field(-1)
                embed.title="Let's delete a role button!"
                embed.description="""Choose the role button to remove from the message.\n\n*Note: This will also delete the button's description from the message!*"""

                self.view.clear_items()
                buttonSelect = RoleButtonSelect(roleMessage=selectedMessage, deletingButton=True)
                self.view.add_item(buttonSelect)
                self.view.message = await interaction.edit_original_response(embed=embed, view=self.view)
            

class RoleButtonSelect(discord.ui.Select):
    def __init__(self, roleMessage: discord.Message, deletingButton=False):
        self.deletingButton = deletingButton
        self.roleMessage = roleMessage

        descriptionLines = roleMessage.embeds[0].description.splitlines()
        self.descriptionLines = roleMessage.embeds[0].description.splitlines(keepends=True)
        descriptionLines.reverse()

        roleMessageView: discord.ui.View = discord.ui.View.from_message(roleMessage)
        self.roleMessageView = roleMessageView

        optionButtonList = []
        for index, button in enumerate(roleMessageView.children):
            emoji = button.emoji
            label = button.label
            description = descriptionLines[len(roleMessageView.children)-index-1]
            value = button.custom_id
            optionButtonList.append(discord.SelectOption(label=label, value=value, description=description[:100], emoji=emoji))

        if optionButtonList:
            # use list comprehension to turn the children into a list of SelectOptions
            self.optionButtonList = optionButtonList
            super().__init__(placeholder='Select a role button...', min_values=1, max_values=1, options=optionButtonList)
        else:
            super().__init__(placeholder='This role message has no role buttons!', min_values=1, max_values=1, disabled=True, options=[discord.SelectOption(label='')])
        

    async def callback(self, interaction: discord.Interaction):
        # Use the interaction object to send a response message containing
        # the user's favourite colour or choice. The self object refers to the
        # Select object, and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        await interaction.response.defer()

        selectedButton = None
        for button in self.optionButtonList:
            if button.value == self.values[0]:
                selectedButton = button
                break
        
        if not selectedButton:
            raise Exception('idk some stuff wonky that role button got messed up')
        else:
            if not self.deletingButton:
                # TODO: update role button - probably choosing a button to update it, so do that
                pass
            else:
                # delete the chosen button and description
                for line in self.descriptionLines:
                    if line.startswith(selectedButton.description):
                        self.descriptionLines.remove(line)
                        break

                newEmbed = self.roleMessage.embeds[0]
                newEmbed.description = ''.join(self.descriptionLines)

                buttonToDelete = discord.utils.get(self.roleMessageView.children, custom_id=self.values[0])
                self.roleMessageView.remove_item(buttonToDelete)
                
                await self.roleMessage.edit(embed=newEmbed, view=self.roleMessageView)

                await interaction.delete_original_response()
                embed = SuccessEmbed(title='Role button removed!')
                successMessage = await interaction.followup.send(embed=embed, ephemeral=True)
                await successMessage.delete(delay=3)

                self.view.stop()

# MARK: EVENTS ------------------------------------------------------------------------------------------------------------

# sets defaults when joining a new guild
@bot.event
async def on_guild_join(guild: discord.Guild):
    info(f"Joined new guild: {guild.name}.")
    await configNewGuilds()
    # additionally, authorize the user that invited the bot
    integrations = await guild.integrations()
    for integration in integrations:
        if isinstance(integration, discord.BotIntegration):
            if integration.application.user.id == bot.user.id:
                inviter = integration.user # returns a discord.User object
                dbUser, _ = await DiscordUser.get_or_create(id=inviter.id)
                dbUser.name = inviter.global_name
                dbUser.username = inviter.name
                await dbUser.save()
                await dbUser.authorizedGuilds.add(await DiscordGuild.get(id=guild.id))
                break

@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    if before.owner_id != after.owner_id:
        info(f"Guild updated owner: {after.name}.")
        await DiscordGuild.update_or_create(id=after.id, defaults={'name': after.name, 'owner': after.owner_id})
        await DiscordUser.update_or_create(id=after.owner_id, defaults={'name': after.owner.global_name, 'username': after.owner.name})

@bot.event
async def on_guild_remove(guild: discord.Guild):
    info(f"Left guild: {guild.name}.")
    dbGuild = await DiscordGuild.get_or_none(id=guild.id)
    # twitch announcements and joinRoles should be deleted by the database ondelete cascade automatically
    # async for announcement in dbGuild.twitchAnnouncements:
    #     await announcement.delete()
    if dbGuild:
        dbGuild.delete()

# on member join give stream role
@bot.event
async def on_member_join(member: discord.Member):
    dbGuild = await DiscordGuild.get_or_none(id=member.guild.id)
    if dbGuild:
        async for role in dbGuild.joinRoles:
            role = member.guild.get_role(role.id)
            if role:
                debug(f'New member {str(member)} ({str(member.id)}) joined server "{str(member.guild)}", giving them role {str(role.name)} ({str(role.id)}).')
                member.add_roles(role)

# error handling for app command errors
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, err):
    error('Error handling "' + (str(interaction.command.name) if interaction.command else str(interaction.data)) + '": ' + str(err))
    error(err, exc_info=True)
    
    embed = BaseEmbed(
        title = 'Oops!',
        description = 'There was an error with your command: ```' + str(err) + '```' +
        'Having trouble? You can always message <@' + str(sketchAuth.discordOwner) +'>!',
        colour = failColour,
        footer = "Don't give up! Try again, I believe in you! :3",
        thumbnail = interaction.guild.icon
    )
    
    try:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.errors.InteractionResponded:
        await interaction.followup.send(embed=embed, ephemeral=True)

# logs when interactions are made, and responds to buttons without needing to re-create views or store roles in DB :3
@bot.event
async def on_interaction(interaction: discord.Interaction):
    info((('Command "' + str(interaction.command.name)) if interaction.command else ('Component "' + str(interaction.data))) + '" invoked by ' + str(interaction.user.name) + ' ('+ str(interaction.user.id) +') on server "' + str(interaction.guild) + '".')
    debug(str(interaction.type))

    if interaction.type is discord.InteractionType.component:
        ctype = discord.enums.try_enum(discord.ComponentType, interaction.data["component_type"])
        debug('component type interacted with: ' + str(ctype))

        if ctype == discord.ComponentType.button:
            debug('component is button!')
            customId: str = interaction.data["custom_id"]
            if customId.startswith('r:'):
                await interaction.response.defer()
                
                # split 0 = r, split 1 = numDuplicate, split 2 = roleId
                customId = customId.split(':')[2]
                debug('ROLE BUTTON PRESSED, ROLE ID: ' + customId)
                newRoleId = int(customId)
                
                # check if we need to cache this guy
                if interaction.channel_id in bot.roleMessageDict:
                    if interaction.message not in bot.roleMessageDict[interaction.channel_id]:
                        warn('Role button pressed from a message that isnt in channel cache, caching message.')
                        bot.roleMessageDict[interaction.channel_id].append(interaction.message)
                else:
                    warn('Role button pressed from a message that isnt in cache at all, caching channel and message.')
                    bot.roleMessageDict[interaction.channel_id] = [interaction.message]

                try:
                    newRole = interaction.guild.get_role(newRoleId)
                    if not newRole:
                        guildRoles = await interaction.guild.fetch_roles()
                        for role in guildRoles:
                            if role.id == newRoleId:
                                newRole = role
                                break
                    if newRole:
                        try:
                            if newRole not in interaction.user.roles:
                                await interaction.user.add_roles(newRole, reason='Self-assigned role added!')
                                roleRemoved = False
                            else:
                                await interaction.user.remove_roles(newRole, reason='Self-assigned role removed!')
                                roleRemoved = True
                        except discord.Forbidden as err:
                            raise discord.Forbidden(err.response, 'I must have "manage_roles" or "admin" permissions to grant/remove a role, and the role must be below my highest role on the servers list of roles!\n\n' + str(err))
                    else:
                        raise ValueError("I couldn't find that role on the server! (Role ID: " + customId + ")")
                    
                    roleView = discord.ui.View.from_message(interaction.message)
                    buttonEmoji = None
                    for child in roleView.children:
                        if child.custom_id == interaction.data["custom_id"]:
                            buttonEmoji = child.emoji
                    
                    if roleRemoved:
                        embed = CancelEmbed(title='Role removed!', description = '# ' + ('' if not buttonEmoji else str(buttonEmoji) + ' ') + str(newRole))
                        successMessage = await interaction.followup.send(embed=embed, ephemeral=True)
                        await successMessage.delete(delay=3)
                    else:
                        embed = SuccessEmbed(title='Role acquired!', description = '# ' + ('' if not buttonEmoji else str(buttonEmoji) + ' ') + str(newRole))
                        successMessage = await interaction.followup.send(embed=embed, ephemeral=True)
                        await successMessage.delete(delay=3)

                except Exception as err:
                    await on_app_command_error(interaction, err)

# MARK: COMMANDS ----------------------------------------------------------------------------------------------------------

# https://gist.github.com/AbstractUmbra/a9c188797ae194e592efe05fa129c57f#file-08-free_function_commands-py
@bot.tree.command(description='Synchronizes application commands with Discord.')
@app_commands.describe(
    mode="Sync method - don't include any guild IDs to target the current guild.",
    guilds='Space separated list of guild IDs - dont specify a mode to re-sync all in list.'
)
@app_commands.guilds(sketchAuth.discordTestServerID)
@app_commands.guild_only()
@app_commands.check(isOwner)
async def sync(
    interaction: discord.Interaction,
    mode: Optional[Literal[
        "Copy global commands to first guild in list and re-sync it.",
        "Clear commands from first guild in list and re-sync it.",
        "Re-sync global commands.",
        "Re-sync each connected guild."
    ]] = None,
    guilds: app_commands.Transform[List[discord.Object], GuildListTransformer] = []
) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)

    if not mode and not guilds:
        debug('Copying globals to and resyncing guild ' + str(interaction.guild))
        bot.tree.copy_global_to(guild=interaction.guild)
        synced = await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"Copied globals to and synced {len(synced)} commands to guild: " + str(interaction.guild))
        return

    if mode:
        if guilds:
            tempGuild = guilds[0]
        else:
            tempGuild = interaction.guild

        if mode == "Copy global commands to first guild in list and re-sync it.":
            debug('Copying globals to and resyncing guild ' + str(tempGuild))
            bot.tree.copy_global_to(guild=tempGuild)
            synced = await bot.tree.sync(guild=tempGuild)
        elif mode == "Clear commands from first guild in list and re-sync it.":
            debug('Clearing commands from and resyncing guild ' + str(tempGuild))
            if tempGuild.id == sketchAuth.discordTestServerID:
                testCommands = [
                    bot.tree.get_command('sync', guild=tempGuild),
                    bot.tree.get_command('crash', guild=tempGuild)
                ]

            bot.tree.clear_commands(guild=tempGuild)

            if tempGuild.id == sketchAuth.discordTestServerID:
                debug('Re-adding special test commands to test server!')
                for command in testCommands:
                    bot.tree.add_command(command,guild=tempGuild)

            await bot.tree.sync(guild=tempGuild)
            synced = []
        elif mode == "Re-sync global commands.":
            debug('Resyncing global commands.')
            synced = await bot.tree.sync()
        else:
            debug('Resyncing all connected discord guilds.')
            ret = 0
            for guild in bot.guilds:
                try:
                    await bot.tree.sync(guild=guild)
                except discord.HTTPException:
                    pass
                else:
                    ret += 1
            await interaction.followup.send(f"Synced the tree to {ret}/{len(bot.guilds)} guilds.")
            return

        await interaction.followup.send(f"Synced {len(synced)} commands {'globally.' if mode == 'Re-sync global commands.' else 'to guild: ' + str(tempGuild)}")
        return

    debug('Resyncing list of provided guilds: ' + str(guilds))
    ret = 0
    for guild in guilds:
        try:
            await bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1
    await interaction.followup.send(f"Synced the tree to {ret}/{len(guilds)} guilds.")

@bot.tree.command(description='Oops :)')
@app_commands.guilds(sketchAuth.discordTestServerID)
@app_commands.guild_only()
@app_commands.check(isOwner)
async def crash(interaction: discord.Interaction) -> None:
    # oh no sketch what are you doing you cant divide by 0
    raise SystemExit

@bot.tree.command(description='Adds a self-assignable role message to the current channel.')
@app_commands.describe(
    title="""The role message's title. Defaults to: "Select your roles!".""",
    description="""The role message's description. Defaults to: "Click a button below to add or remove roles.".""",
    colour="""The role message's sidebar colour (in hex). Defaults to: \"""" + defaultColourHex + """" (Alastair red! :3)"""
)
@app_commands.guild_only()
@app_commands.default_permissions(manage_roles=True)
async def addrolemessage(
    interaction: discord.Interaction,
    title: str = "Select your roles!",
    description: str = "Click a button below to add or remove roles.",
    colour: str = defaultColourHex
) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)

    embed = discord.Embed(
        title=title,
        description=description+'\n',
        colour=discord.Colour.from_str(colour)
    )
    # store roleMessage.id in database
    roleMessage = await interaction.channel.send(embed=embed)
    debug('created role messages: ' + str(roleMessage))

    embed = SuccessEmbed(title='Role message created!')
    successMessage = await interaction.followup.send(embed=embed, ephemeral=True)
    await successMessage.delete(delay=3)
    debug('sent success message:' + str(successMessage))

    view = AddRoleView(roleMessage=roleMessage, deleteOnCancel=True)
    embed = await view.getEmbed(BaseEmbed(
        title="Let's add the first role!",
        description="""To get started, we'll need to add a role button to the self-role message that I just created above.\n\nDiscord only lets me have 25 options in a list... so use the buttons to navigate pages if you have more roles than that!\n\n(also tell Discord that is insane?? ((they won't let me in to talk after they caught me in the dumpster)))""",
        thumbnail = interaction.guild.icon
    ))
    view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

@bot.tree.command(description='Adds a new button to a self-role message in the current channel.')
@app_commands.guild_only()
@app_commands.default_permissions(manage_roles=True)
async def addrolebutton(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)

    # send a RoleMessageSelect based on the AddRoleView
    view = SelectRoleMessageView(channel=interaction.channel)
    embed = await view.getEmbed(BaseEmbed(
        title="Choose the role message to add a button to!",
        description="""To add a button, please select the self-assignable role message from this channel that you want to add the button to.\n\nDiscord only lets me have 25 options in a list... so use the buttons to navigate pages if you have more messages than that!\n\n*Note: If it says there are no role messages, just use a button on an existing role message in this channel and then try this command again.*""",
        thumbnail = interaction.guild.icon
    ))
    view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

@bot.tree.command(description='Deletes a button from a self-role message in the current channel.')
@app_commands.guild_only()
@app_commands.default_permissions(manage_roles=True)
async def deleterolebutton(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)

    view = SelectRoleMessageView(channel=interaction.channel, deletingButton=True)
    embed = await view.getEmbed(BaseEmbed(
        title="Choose the role message to remove a button from!",
        description="""To remove a button, please select the self-assignable role message from this channel that you want to remove the button from.\n\nDiscord only lets me have 25 options in a list... so use the buttons to navigate pages if you have more messages than that!\n\n*Note: If it says there are no role messages, just use a button on an existing role message in this channel and then try this command again.*""",
        thumbnail = interaction.guild.icon
    ))
    view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)