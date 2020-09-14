#!/usr/bin/env python

import argparse
import logging
from mixtt.mixtt import MIXTT
import sys


DEFAULT_LOG_FILE = "/var/log/mixtt/mixtt.log"

def parse_args(sys_args):
    """ Parse arguments for the topology tester

    Args:
        sys_args (sys.args): System arguments to parse

    Returns:
        argparse.Namespace: command line arguments
    """

    args = argparse.ArgumentParser(
        prog='mixtt',
        description='Mininet IXP Topology Tester'
    )
    group = args.add_mutually_exclusive_group()
    group.add_argument(
        '-t', '--topology-file',
        action='store',
        help='Reads topology information from a json file'
    )
    group.add_argument(
        '-j', '--json-topology',
        action='store',
        help='Reads topology information from a json string (experimental)'
    )
    args.add_argument(
        '-c', '--cli',
        action='store_true',
        help='Enables CLI for debugging',
    )
    args.add_argument(
        '-p', '--ping',
        action='store',
        help='Set the ping count used in pingall',
        default='1'
    )
    args.add_argument(
        '-n', '--no-redundancy',
        action='store_true',
        help='Disables the link redundancy checker (Used for testing p4)'
    )
    args.add_argument(
        '--thrift-port',
        action="store",
        help="Thrift server port for p4 table updates",
        default="9090"
    )
    args.add_argument(
        '--p4-json',
        action='store',
        help="Config json for p4 switches"
    )
    args.add_argument(
        '-l', '--log-level',
        action='store',
        help='Sets the log level'
    )
    args.add_argument(
        '--log-file',
        action='store',
        help="Set location for log file",
    )

    return args.parse_args(sys_args)

def main():
    setup_logging()
    args = parse_args(sys.argv[1:])

    MIXTT().start(args)
    

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