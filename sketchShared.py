import sys, io, datetime, traceback, inspect
import logging, logging.handlers

global sketchUncaughtException
sketchUncaughtException = None

# defines my own logging formatter class that manipulates module text and date format, as well as retrieves the actual raising module's name during an uncaught exception
class SketchLogFormatter(logging.Formatter):
    # replaces default module with uppercase module, replaces "sketch" with main or removes it from prefix
    def format(self, record):
        global sketchUncaughtException
        if sketchUncaughtException:
            # get the stack info from the last traceback entry, and find filename
            modulePath = traceback.extract_tb(sketchUncaughtException)[-1].filename
            # find the module name from the filename path
            moduleName = inspect.getmodulename(modulePath)
            if moduleName:
                # overwrite the record's module name with the real module name, because otherwise it will look like it's coming from here
                record.module = moduleName
        
        record.module = record.module.upper()

        if record.module != 'SKETCH' and record.module.startswith('SKETCH'):
            # just remove sketch prefix from modules so its nicer to read
            record.module = record.module.removeprefix('SKETCH')

        if record.module == 'SHARED' and (record.name == 'stdout' or record.name == 'stderr'):
            # replace level with STDOUT/STDERR and remove the module from the string format, because we append the real module during stdout/stderr redirection. if we dont do it that way, finding the calling function is wayyy harder
            record.levelname = record.name.upper()
            self._fmt = self._fmt.replace('%(module)s: ', '')
            self._style._fmt = self._style._fmt.replace('%(module)s: ', '')
        else:
            if '%(module)s' not in self._fmt:
                # set the string format back to normal if the module got removed from processing stdout/stderr previously
                self._fmt = self._fmt.replace('%(message)s', '%(module)s: %(message)s')
                self._style._fmt = self._style._fmt.replace('%(message)s', '%(module)s: %(message)s')

        # call the original formatting function to handle adding time and etc.
        orig = logging.Formatter.format(self, record)

        # append the message prefix to any newlines that are going to be printed
        splitOrig = orig.split('\n')
        origPrefix = orig.partition(record.message)[0]
        # if the module was removed, then we don't have an accurate one
        if '%(module)s' not in self._fmt:
            # have to get the module name from the message since we dont get it here
            partMessage = record.message.partition(': ')
            origPrefix = '\n' + origPrefix + partMessage[0] + partMessage[1]
        else:
            origPrefix = '\n' + origPrefix
        if len(splitOrig) > 1:
            # put the message back together with newlines and prefix appended
            orig = origPrefix.join(splitOrig)
        return orig

    # replaces default time formatting with RFC 3339 compliant format
    def formatTime(self, record, datefmt=None):
        return (datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).astimezone().isoformat())

# Use the original sys.__stdout__ to write to stdout for this handler, as sys.stdout is overriden to go to logger
class DefaultStreamHandler(logging.StreamHandler):
    def __init__(self, stream=sys.__stdout__):
        super().__init__(stream)

# class that replaces stderr & stdout
class LoggerWriter(io.IOBase):
    # logger_name: Name to give the logger (e.g. 'stderr')
    # log_level: The log level, e.g. logging.DEBUG / logging.INFO that the MESSAGES should be logged at.
    def __init__(self, logger_name: str, log_level: int):
        # uses the root logger's level and handlers/formatters because we aren't specifying any
        self.std_logger = logging.getLogger(logger_name)
        # the level msgs will be logged at when used lated in the write function
        self.level = log_level
        self.buffer = []

    # stdout/stderr logs one line at a time, rather than 1 message at a time, so this aggregates multi-line messages into 1 log call
    def write(self, msg: str):
        msg = msg.decode() if issubclass(type(msg), bytes) else msg

        if not msg.endswith('\n'):
            # append the message to the buffer if it isn't a finished line
            return self.buffer.append(msg)

        self.buffer.append(msg.rstrip('\n'))
        message = ''.join(self.buffer)

        # append the calling module's name to this message before logging it, because its very simple to get the calling function here rather than in the formatter
        currentFrame = sys._getframe()
        if currentFrame:
            # gets the filename from the previous frame's code file
            callingFramePath = currentFrame.f_back.f_code.co_filename
            moduleName = inspect.getmodulename(callingFramePath)
            if moduleName:
                # massage the module name, then put it into the message
                if moduleName != 'sketch' and moduleName.startswith('sketch'):
                    moduleName = moduleName.removeprefix('sketch')
                message = moduleName.upper() + ': ' + message

        # log the line and clear the buffer
        self.std_logger.log(self.level, message)
        self.buffer = []

# stores uncaught exception traceback in a global variable so that it can be retrieved and used to get the actual raising module's name since python completely obliterates the stack and there is literally no way to get info about the current exception / previous exception if it was uncaught
def handleUncaughtExceptions(eType, eValue, eTraceback):
    global sketchUncaughtException
    sketchUncaughtException = eTraceback
    logging.critical("FATAL UNCAUGHT EXCEPTION:", exc_info=(eType, eValue, eTraceback))

# set up the root file logger that the base and future loggers copy
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.DEBUG)
rootHandler = logging.handlers.RotatingFileHandler('sketch.log', maxBytes=1000000, backupCount=25)
rootHandler.setLevel(logging.DEBUG)
fileLogFormat = SketchLogFormatter('%(asctime)s %(levelname)-8s %(module)s: %(message)s')
rootHandler.setFormatter(fileLogFormat)

# set up the console logger so the console can output the same info that goes to the log
console = DefaultStreamHandler()
console.setLevel(logging.DEBUG)
consoleLogFormat = SketchLogFormatter('%(levelname)-8s %(module)s: %(message)s')
console.setFormatter(consoleLogFormat)

# add the file and console logger handlers to the root so they will always get output
rootLogger.addHandler(rootHandler)
rootLogger.addHandler(console)

# overriding stdout and stderr to write to the root logger, the levels I set dont really matter because I override them in the formatter with STDOUT/STDERR instead of info/error. the original stdout/stderr are at sys.__stdout__ and sys.__stderr__ if needed
sys.stdout = LoggerWriter("stdout", logging.INFO)
sys.stderr = LoggerWriter("stderr", logging.ERROR)
# overriding the uncaught exception hangle with my own that lets me get the module info into the logger, because otherwise it is impossible. the original excepthook is at sys.__excepthook__(exc_type, exc_value, exc_traceback) if needed
sys.excepthook = handleUncaughtExceptions

# make it easier to type these than doing logging.debug()
debug = logging.debug
info = logging.info
warn = logging.warning
error = logging.error
critical = logging.critical