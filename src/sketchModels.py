from tortoise import fields, models

# MySQL/mariaDB unsigned big integer (range 0 to 18446744073709551615).
class UnsignedBigIntField(fields.BigIntField):
    SQL_TYPE = "BIGINT UNSIGNED"
    
    @property
    def constraints(self) -> dict:
        return {
            "ge": 0,
            "le": 18446744073709551615,
        }
    
    class _db_mysql:
        GENERATED_SQL = "BIGINT UNSIGNED NOT NULL PRIMARY KEY AUTO_INCREMENT"


class DiscordGuild(models.Model):
    # generated is set to True automatically on an intfield set as primarykey, which means it normally autoincrements
    id = UnsignedBigIntField(primary_key=True, generated=False)
    # utfmb4 default encoding uses 4 bytes per character, max for a varchar is 65535 bytes, so max of 16383 chars
    name = fields.CharField(max_length=100, null=True)
    # the owner of the server
    owner = UnsignedBigIntField()
    
    deleteOldAnnouncements = fields.BooleanField(default=False)
    spamProtectionAnnounceDelay = fields.IntField(default=10)
    timeZone = fields.CharField(max_length=100, default='US/Central')
    
    # https://stackoverflow.com/questions/63221321/discord-py-how-to-get-the-user-who-invited-added-the-bot-to-his-server-soluti
    # https://discordpy.readthedocs.io/en/latest/api.html?highlight=discord%20guild%20integrations#discord.Guild.integrations
    # get the user that invited the bot, and make them an authorized user for this server
    authorizedUsers: fields.ManyToManyRelation["DiscordUser"]
    twitchAnnouncements: fields.ReverseRelation["TwitchAnnouncement"]
    joinRoles: fields.ReverseRelation["DiscordJoinRole"]

class DiscordUser(models.Model):
    id = UnsignedBigIntField(primary_key=True, generated=False)
    name = fields.TextField(null=True)
    username = fields.TextField(null=True)
    accessToken = fields.TextField(null=True)
    refreshToken = fields.TextField(null=True)
    expiryTime = fields.DatetimeField(null=True)
    state = fields.TextField(null=True)
    sessionID = fields.TextField(null=True)
    profileImageURL = fields.TextField(null=True)

    authorizedGuilds: fields.ManyToManyRelation["DiscordGuild"] = fields.ManyToManyField('models.DiscordGuild', related_name='authorizedUsers', through='discordauthorizedguild_user')
    
class DiscordJoinRole(models.Model):
    id = UnsignedBigIntField(primary_key=True, generated=False)
    name = fields.TextField(null=True)
    guild: fields.ForeignKeyRelation["DiscordGuild"] = fields.ForeignKeyField('models.DiscordGuild', related_name='joinRoles', on_delete=fields.OnDelete.CASCADE)
        
class TwitchAnnouncement(models.Model):
    id = fields.IntField(primary_key=True)
    streamName = fields.CharField(max_length=100, null=False)
    streamID = UnsignedBigIntField(null=True)
    profileImageURL = fields.TextField(null=True)
    offlineImageURL = fields.TextField(null=True)
    # parse this to get any roles that should be mentioned, etc. default will be no role mention
    announcementText = fields.TextField()
    guild: fields.ForeignKeyRelation["DiscordGuild"] = fields.ForeignKeyField('models.DiscordGuild', related_name='twitchAnnouncements', on_delete=fields.OnDelete.CASCADE, null=True)
    channelID = UnsignedBigIntField()
    messageID = UnsignedBigIntField(null=True)
    ended = fields.DatetimeField(null=True)