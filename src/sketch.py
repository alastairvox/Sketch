import sketchShared
from sketchShared import debug, info, warn, error, critical
import asyncio, signal, atexit, sys
import sketchDiscord, sketchTwitch, sketchYoutube, sketchServer, sketchDatabase

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
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⠋⣤⣤⣌⠙⠿⠿⠿⠿⠿⠿⠟⢉⣠⣤⣌⠹⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⡇⢸⣿⠉⢻⣷⣦⣶⣶⣶⣶⣶⣴⣿⠋⢹⣿⠀⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⡿⠁⣾⣿⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣾⣿⣆⠸⣿⣿⣿⣿⣿
⣿⣿⣿⠟⢁⣾⡿⠟⠛⠛⠿⣿⣿⣿⣿⣿⣿⣿⠿⠛⠛⠿⣿⣦⠙⢿⣿⣿⣿
⣿⠟⣁⣴⣿⡿⠀⠀⠀⠀⠀⠈⢻⣿⣿⣿⠏⠀⠀⠀⠀⠀⠘⣿⣷⣄⡙⢻⣿    Sketch v1.10 (Roles+Web+Twitch)
⣿⣄⡉⠛⢿⣷⠀⠀⢸⣦⡀⠀⠀⢿⣿⡏⠀⠀⣠⣾⠀⠀⢠⣿⠿⠋⣉⣴⣿    Seek Knowledge Everywhere, Tiny Computer Helper
⣿⠋⢠⣶⣿⣿⣷⣄⠘⠿⣿⡆⠀⢸⣿⠀⠀⣼⡿⠟⢀⣠⣿⣿⣷⣦⡌⢻⣿    Alastair Vox (alastairvox.com)
⣿⣷⣤⣈⡙⠻⣿⣿⣷⣄⠀⠻⠀⠀⣿⠀⠸⠁⢀⣴⣿⣿⡿⠟⢉⣠⣴⣾⣿
⣿⣿⣿⣿⣿⣶⣄⠙⢿⣿⣷⠀⠀⠀⣿⠀⠀⠠⣿⣿⠟⢁⣤⣾⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣦⡈⠁⠀⢀⣼⣿⣄⠀⠀⠉⣠⣴⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⣀⠛⠿⠿⠟⢃⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣶⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
""")
    
    try:
        # append the parent directory to the path of modules that can be searched
        sys.path.append('./')
        # overrides certain values in sketchAuth for dev environment
        import sketchDevAuth
        sketchShared.dev = True
        warn('MODE: DEVELOPMENT')
    except ImportError:
        # not dev, dont do anything
        warn('MODE: PRODUCTION')
        pass

    # register some handlers for most cases where the program is killed or exits
    atexit.register(exitHandler)
    signal.signal(signal.SIGTERM, exitHandler)
    signal.signal(signal.SIGINT, exitHandler)

    # gets the current event loop or creates one (there can only ever be one running event loop)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        # Set it as the current event loop so that it will be returned when asyncio.get_running_loop is called:
        asyncio.set_event_loop(loop)

    # runs this until its done, so that we can make sure the database is fully set up before all the other services run
    loop.run_until_complete(sketchDatabase.summon())

    # schedules a task to run on the event loop next time the event loop checks for stuff, unless the event loop got closed!! (which is why we run forever, otherwise it wont even start them)
    loop.create_task(sketchDiscord.summon())
    loop.create_task(sketchTwitch.summon())
    loop.create_task(sketchServer.summon())
    loop.create_task(sketchYoutube.youtubePrepareAllResubs())
    # makes the event loop run forever (this is blocking), so any current and future scheduled tasks will run until we explicitly tell the loop to die with loop.stop()
    loop.run_forever()

if __name__ == '__main__':
    main()