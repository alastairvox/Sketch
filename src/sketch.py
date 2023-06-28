import sketchShared
from sketchShared import debug, info, warn, error, critical
import asyncio, signal, atexit
import sketchDiscord, sketchYoutube, sketchServer, sketchDatabase

def exitHandler(*args):
    warn("""
----------------------------------------------------------------------------
----------------------------------------------------------------------------
                                SKETCH DIES
----------------------------------------------------------------------------
----------------------------------------------------------------------------
""")

def main():
    warn("""
----------------------------------------------------------------------------
----------------------------------------------------------------------------
                                SKETCH LIVES
----------------------------------------------------------------------------
----------------------------------------------------------------------------
""")
    
    # register some handlers for most cases where the program is killed or exits
    atexit.register(exitHandler)
    signal.signal(signal.SIGTERM, exitHandler)
    signal.signal(signal.SIGINT, exitHandler)

    # gets the current event loop or i guess creates one (there can only ever be one running event loop)
    loop = asyncio.get_event_loop()
    # loop.run_until_complete(sketchDatabase.summon())
    # schedules a task to run on the event loop next time the event loop checks for stuff, unless the event loop got closed!! (which is why we run forever, otherwise it wont even start them)
    loop.create_task(sketchServer.summon())
    loop.create_task(sketchDiscord.summon())
    # makes the event loop run forever (this is blocking), so any current and future scheduled tasks will run until we explicitly tell the loop to die with loop.stop()
    loop.run_forever()

if __name__ == '__main__':
    main()