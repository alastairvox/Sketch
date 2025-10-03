import sketchShared
from sketchShared import debug, info, warn, error, critical
from tortoise.models import Model
from tortoise import fields, Tortoise, run_async
import datetime, logging
import sketchAuth

# Initialize Tortoise ORM
async def init():
    await Tortoise.init(
        # Database connection configuration
        db_url= f"mysql://sketch:{sketchAuth.dbPassword}@{sketchAuth.dbHost}:{sketchAuth.dbPort}/sketch",
        # Path to your models module
        modules={'models': ['sketchModels']}
    )
    # Generate schemas for all models, safe=True means it will only recreate the tables when they arent there
    await Tortoise.generate_schemas(safe=True)

# Close connections
async def close():
    await Tortoise.close_connections()

# https://github.com/tortoise/tortoise-orm
# https://betterstack.com/community/guides/scaling-python/tortoise-orm/
async def summon():
    info('Summoning...')

    # https://tortoise.github.io/logging.html
    logging.getLogger("tortoise.db_client").setLevel(logging.DEBUG)
    logging.getLogger("tortoise").setLevel(logging.DEBUG)
    
    await init()