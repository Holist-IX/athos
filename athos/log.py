""" Logging function for Topology tester """

import logging
import os
import types
from logging import FileHandler, Formatter, Logger, StreamHandler, debug
from mininet.log import StreamHandlerNoNewline, lg, setLogLevel


DEFAULT_LOG_PATH = "/var/log/athos"
DEFAULT_LOG_FILE = DEFAULT_LOG_PATH + "/athos.log"
DEFAULT_MN_LOG_FILE = DEFAULT_LOG_PATH + "/mininet.log"
LOGMSGFORMAT = '%(asctime)s %(name)s %(levelname)s %(message)s'

LEVELS = {  'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
}

def get_logger(log_level='info', logname='athos',
    log_file=DEFAULT_LOG_FILE, console=True):

    log_lvl = LEVELS.get(log_level) if log_level in LEVELS else logging.INFO

    # Needed to be able to use more than 1 log with mininet
    logging.basicConfig(
        level=log_lvl,
        force=True
    )
    
    if logname is DEFAULT_LOG_FILE:
        create_default_path()
    logger = logging.getLogger(logname)

    logger_fhandler = logging.FileHandler(log_file)

    logger_fhandler.setFormatter(
        logging.Formatter(LOGMSGFORMAT, '%b %d %H:%M:%S'))
    logger_fhandler.setLevel(log_lvl)
    logger.addHandler(logger_fhandler)
    logger.propagate = False

    return logger


def set_mininet_log_file(log_level='info', console=True,
        log_file=DEFAULT_MN_LOG_FILE):
    fh = FileHandlerNoNewLine(log_file)
    fh.setFormatter(Formatter('%(message)s'))
    lg.addHandler( fh )

    setLogLevel('info')

    if not console:
        lg.handlers = [
            h for h in lg.handlers if not isinstance(h, StreamHandlerNoNewline)]
            

def create_default_path():
    """ Creates the folder for the default log path """
    
    if os.path.exists(DEFAULT_LOG_PATH) and os.path.isfile(DEFAULT_LOG_FILE):
        return
    else:
        print("Default log path not found creating")
        os.makedirs(DEFAULT_LOG_PATH)
        return
        

class FileHandlerNoNewLine(logging.FileHandler ):
    """ FileHandler that doesn't print newlines by default
        This is to make the logging work better with the way that mininet logs
        to the console, and we can get all those logs in a file """

    def emit( self, record ):
        """Emit a record.
           If a formatter is specified, it is used to format the record.
           The record is then written to the stream with a trailing newline
           [ N.B. this may be removed depending on feedback ]. If exception
           information is present, it is formatted using
           traceback.printException and appended to the stream."""
        try:
            msg = self.format( record )
            fs = '%s'  # was '%s\n'
            if not hasattr( types, 'UnicodeType' ):  # if no unicode support...
                self.stream.write( fs % msg )
            else:
                try:
                    self.stream.write( fs % msg )
                except UnicodeError:
                    self.stream.write( fs % msg.encode( 'UTF-8' ) )
            self.flush()
        except ( KeyboardInterrupt, SystemExit ):
            raise
        except:
            self.handleError( record )