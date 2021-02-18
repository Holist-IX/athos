#!/usr/bin/python3

import argparse
from athos.log import get_logger, set_mininet_log_file
from athos.athos import ATHOS
import sys


def parse_args(sys_args):
    """ Parse arguments for the topology tester

    Args:
        sys_args (sys.args): System arguments to parse

    Returns:
        argparse.Namespace: command line arguments
    """

    args = argparse.ArgumentParser(
        prog='athos',
        description='Automated mininet topology evaluator'
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
    args.add_argument(
        '-s','--script',
        action="store",
        help="Runs a script before doing standard testing"
    )

    return args.parse_args(sys_args)


def main():

    args = parse_args(sys.argv[1:])
    logger = get_logger()
    set_mininet_log_file()
    ATHOS().start(args, logger)

if __name__ == '__main__':
    main()