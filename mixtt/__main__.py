#!/usr/bin/env python

import logging
import sys
from mixtt import MIXTT

def main():
    setup_logging()
    MIXTT().start(sys.argv)

def setup_logging():
    logname = "mininet"
    logger = logging.getLogger(logname)
    logger_handler = logging.FileHandler('/var/log/mixtt/mixtt.log')
    log_fmt = '%(asctime)s %(name)-6s %(levelname)-8s %(message)s'
    logger_handler.setFormatter(
        logging.Formatter(log_fmt, '%b %d %H:%M:%S'))
    logger.addHandler(logger_handler)
    logger_handler.setLevel('INFO')
    # setLogLevel('info')

if __name__ == '__main__':
    main()