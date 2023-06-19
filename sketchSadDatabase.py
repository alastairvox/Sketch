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

async def updateTableInfo():
    global validTables
    info('Updating valid tables...')
    # get a list of tables from the database
    async with db.cursor() as cursor:
        await cursor.execute("""SHOW TABLES FROM sketch""")
        data = await cursor.fetchall()
        # returns a list of dicts
        for entry in data:
            # each dict only has one entry
            for key, value in entry.items():
                validTables[value] = {}
                # get each table's column names from the database
                await cursor.execute("""SHOW COLUMNS FROM sketch.""" + value)
                columnData = await cursor.fetchall()
                tablePrimaryKeyList = []
                for column in columnData:
                    # store the column type for truncating / formatting dates
                    validTables[value][column['Field']] = column['Type']
                    # will be '' if not a primary key
                    if column['Key']:
                        tablePrimaryKeyList.append(column['Field'])

    debug('Tables from DB: ' + str(validTables))
    return

class SketchDbObj():
    # we use this as an alternative to init since you cant have an asynchronous init method
    # the class method decorator means this function refers to the class itself, not the object instance
    @classmethod
    async def create(cls, table, dict=None, list=None):
        self = SketchDbObj()
        self.list = []
        # validate that the table exists
        if table in validTables:
            self.table = table
            debug('Valid table!')
            if dict:
                await self.add(dict)
                return self
            if list:
                await self.replace(list)
                return self
        else:
            raise ValueError('invalid table (table not found in database): ' + table)
        return self
    
    async def add(self, dict):
        debug('Dict to add: ' + str(dict))
        for key, value in dict.items():
            if key in validTables[self.table].keys():
                if validTables[self.table][key].startswith('varchar'):
                    truncateLength = int(validTables[self.table][key].split('(')[1].split(')')[0])
                    dict[key] = value[:truncateLength]
                    debug(str(key) + ': ' + str(dict[key]))
            else:
                raise ValueError('invalid column name (column not found in table): ' + key)

    async def replace(self, list=[]):
        debug('Replacting list with: ' + str(list))
        self.list = []
        for dict in list:
            self.add(dict)

    # https://aiomysql.readthedocs.io/en/stable/cursors.html#Cursor.executemany
    async def store(self):
        info('Storing rows in database: ' + str(self.list))
        async with db.cursor() as cursor:
            for row in self.list:
                # Compose a string of quoted column names
                cols = ','.join([f'`{key}`' for key in row.keys()])

                # Compose a string of placeholders for values
                vals = ','.join(['%s'] * len(row))

                # Create the SQL statement
                stmt = 'INSERT INTO ' + self.table + f' ({cols}) VALUES ({vals})'

                # Execute the statement, delegating the quoting of values to the connector
                await cursor.execute(stmt, tuple(row.values()))

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
    await updateTableInfo()

    return

global db
db = None
global validTables
validTables = {}

# # fetch all results
# r = await cursor.fetchone()
# print(r)
# # {'age': 20, 'DOB': datetime.datetime(1990, 2, 6, 23, 4, 56),
# # 'name': 'bob'}
# print(r.age)
# # 20
# print(r.foo)
# # None