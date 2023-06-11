import asyncio
import sketchShared
from sketchShared import debug, info, warn, error, critical
import sketchYoutube

def main():
    info('Sketch lives.')

    # gets the current event loop or i guess creates one (there can only ever be one running event loop)
    loop = asyncio.get_event_loop()
    loop.run_forever()

if __name__ == '__main__':
    main()