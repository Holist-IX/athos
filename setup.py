#!/usr/bin/python3


import errno
import os
import sys
from setuptools import setup
from pkg_resources import resource_filename
from shutil import copyfile


def setup_configs():
    """ Sets up the defualt log and config paths """
    log_dir = '/var/log/mixtt'
    mixtt_log = '/var/log/mixtt/mixtt.log'
    mn_log = '/var/log/mixtt/mininet.log'
    conf_dir = '/etc/mixtt/'
    conf_file = '/etc/mixtt/topology.json'
    umbrella_json = '/etc/mixtt/umbrella.json'
    defualt_umbrella = resource_filename(__name__, 'etc/mixtt/umbrella.json')
    default_conf = resource_filename(__name__, 'etc/mixtt/topology.json')

    try:
        if not os.path.exists(log_dir):
            print(f"Creating log dir: {log_dir}")
            os.makedirs(log_dir)
        if not os.path.isfile(mixtt_log):
            open(mixtt_log, 'a').close()
        if not os.path.isfile(mn_log):
            open(mn_log, 'a').close()
        if not os.path.exists(conf_dir):
            print(f"Creating config dir: {conf_dir}")
            os.makedirs(conf_dir)
        if not os.path.isfile(conf_file):
            print("Setting up default config for topology")
            print(f"Copying: {default_conf} to {conf_file} ")
            copyfile(default_conf, conf_file)
        if not os.path.isfile(umbrella_json):
            print("Setting up default p4 umbrella json")
            print(f"Copying: {defualt_umbrella} to {umbrella_json}")
            copyfile(defualt_umbrella, umbrella_json)

    except OSError as exc_info:
        if exc_info.errno == errno.EACCES:
            print(f"Permission denied when creating {exc_info.filename}\n" +
                    "Are you running as root?")
        else:
            raise


setup(
    name='mixtt',
    setup_requires=['pbr>=1.9', 'setuptools>=17.1'],
    python_requires='>=3.6',
    pbr=True
)

if 'install' in sys.argv:
    setup_configs()