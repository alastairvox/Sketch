import sketchShared
from sketchShared import debug, info, warn, error, critical
import asyncio, asyncmy
import sketchAuth

# can use either asyncmy (newer, intended to be faster) or aiomysql for asynchronous mysql/mariadb
# aiomysql is unmaintained...? asyncmy is "api compatible" with aiomysql so just use asyncmy with aiomysql docs i guess 😭
# https://www.digitalocean.com/community/tutorials/how-to-install-mariadb-on-ubuntu-22-04
# https://aiomysql.readthedocs.io/en/stable/connection.html#connection
# https://github.com/long2ice/asyncmy

# Dict that can get attribute by dot, and doesn't raise KeyError
class AttrDict(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return None

# Custom cursor class that uses attribute dict
class AttrDictCursor(asyncmy.cursors.DictCursor):
    dict_type = AttrDict

# creates database if it doesn't exist, should pretty much never need to be called
async def createDatabase():
    warn('Creating/replacing main Sketch database...')

    # https://aiomysql.readthedocs.io/en/stable/cursors.html#Cursor.execute
    # https://www.tutorialspoint.com/mariadb/mariadb_data_types.htm
    # https://www.techonthenet.com/mariadb/primary_keys.php
    async with db.cursor() as cursor:
        await cursor.execute("""CREATE DATABASE IF NOT EXISTS sketch""")
        await cursor.execute("""
            CREATE OR REPLACE TABLE sketch.users(
                sketchId INT AUTO_INCREMENT PRIMARY KEY,
                userName VARCHAR(50) DEFAULT ''
            );
        """)
        await cursor.execute("""
            CREATE OR REPLACE TABLE sketch.connections(
                sketchId INT NOT NULL,
                serviceName VARCHAR(50) NOT NULL,
                serviceId VARCHAR(255) NOT NULL,
                PRIMARY KEY (sketchId, serviceName, serviceId),
                FOREIGN KEY (sketchId) REFERENCES sketch.users (sketchId) ON DELETE CASCADE ON UPDATE CASCADE
            );
        """)
        await cursor.execute("""
            CREATE OR REPLACE TABLE sketch.discord(
                discordId INT NOT NULL,
                guildId INT NOT NULL,
                PRIMARY KEY (discordId, guildId)
            );
        """)
        await cursor.execute("""
            CREATE OR REPLACE TABLE sketch.youtube(
                youtubeId VARCHAR(255) NOT NULL,
                channelId VARCHAR(50) NOT NULL,
                refreshToken VARCHAR(5000),
                accessToken VARCHAR(5000),
                accessExpires DATETIME,
                scheduling BOOLEAN NOT NULL DEFAULT false,
                monitoring BOOLEAN NOT NULL DEFAULT false,
                PRIMARY KEY (youtubeId, channelId)
            );
        """)
        await cursor.execute("""
            CREATE OR REPLACE TABLE sketch.youtubeVideos(
                videoId VARCHAR(50) PRIMARY KEY,
                channelId VARCHAR(50) NOT NULL,
                title VARCHAR(100),
                privacyStatus VARCHAR(50),
                thumbnailUrl VARCHAR(2083),
                publishAt DATETIME
            );
        """)

        await db.commit()

async def connectDatabase():
    global db
    info('Connecting database...')

    try:
        db = await asyncmy.connect(
            host = 'localhost',
            port = 3306,
            user = 'sketch',
            password = sketchAuth.dbPassword,
            cursor_cls = AttrDictCursor
        )
    except Exception as error:
        error('Error connecting database: ' + str(error))

    if db.connected:
        # theres no way to get just the port number from asyncmy lol
        info('Connected to database on port ' + db.host_info.split(':', 1)[1] + '.')
        debug('Connection: ' + str(db.host_info) + ' running ' + str(db.server_version)+ '.')
    else:
        error('Error connecting database. Connection function ran, but connected is False afterward.')

    sketchShared.db = db
    return

global db

# # fetch all results
# r = await cursor.fetchone()
# print(r)
# # {'age': 20, 'DOB': datetime.datetime(1990, 2, 6, 23, 4, 56),
# # 'name': 'bob'}
# print(r.age)
# # 20
# print(r.foo)
# # None