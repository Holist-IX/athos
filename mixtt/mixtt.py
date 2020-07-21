#!/usr/bin/python3

""" Mininet IXP Topology tester

Generates a mininet topology based on the info gathered from IXP Manager and the
faucet config generator
"""

import mininet.node
import sys
import argparse
import json
import logging
from logging import Logger, warning
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel, info, debug, error, warn, output, MininetLogger
from mininet.node import RemoteController
from mininet.cli import CLI

from sys import argv

DEFAULT_INPUT_FILE = "/etc/mixtt/topology.json"
DEFAULT_LOG_FILE = "/mixtt/ixpman_files/output.txt"
LOGMSGFORMAT = '%(message)s'

class MIXTT():
    """ Mininet IXP topology tester. 
    
        Takes json with topology information and builds a network based on this.
        It will check the reachability of all hosts as well as redundancy is 
        working by turning off each link between switches and validates that 
        hosts are still able to communicate. """

    def __init__(self):
        self.net = None
        self.network_matrix = None
        self.hosts_matrix = None
        self.switch_matrix = None
        self.switch_dps = None
        self.vlan_matrix = {}
        self.ping_count = 1


    def build_network(self):
        """ Builds a mininet network based on the network matrix that's been 
            given """

        topo = self.MyTopo( hosts_matrix=self.hosts_matrix, 
                            switch_matrix=self.switch_matrix,
                            switch_dps=self.switch_dps)
        self.net = Mininet(
            topo=topo, 
            controller=RemoteController(
                name="faucet",
                ip="127.0.0.1",
                port=6653
            ))
        

    def test_network(self):
        """ Sets up the network and tests that all hosts can ping each other in
            ipv4 and ipv6. Also tests failover by disabling links between 
            switches """
        self.pingAllV4()
        self.pingAllV6()
        for link in self.switch_matrix:
            s1, s2 = link[0], link[2]
            output(f"Setting link between {s1} and {s2} down\n")
            self.net.configLinkStatus(s1, s2, "down")
            self.pingAllV4()
            self.pingAllV6()
            output(f"Setting link between {s1} and {s2} up\n")
            self.net.configLinkStatus(s1, s2, "up")
            self.pingAllV4()
            self.pingAllV6()


    def cleanup_ips(self):
        """ Cleans up ip addresses, in particular hosts with multiple interfaces
            and vlans """
        port = 0
        connected_sws = {}
        
        self.vlan_matrix["none"] = []
        for host in self.hosts_matrix:
            port = 0
            hname = host["name"]
            for iface in host["interfaces"]:
                if iface["switch"] not in connected_sws:
                    connected_sws[iface["switch"]] = {}
                if iface["swport"] not in connected_sws[iface["switch"]]:
                    connected_sws[iface["switch"]][iface["swport"]] = port
                    if "vlan" in iface:
                        self.add_vlan(hname, iface, port)
                    else:
                        h = {"name": hname}
                        if "ipv4" in iface:
                            h["ipv4"] = iface["ipv4"]
                        if "ipv6" in iface:
                            self.add_ipv6(hname, f"{hname}-eth{port}", iface)
                            h["ipv6"] = iface["ipv6"]
                        self.vlan_matrix["none"].append(h)
                    port+=1
                    continue
                if iface["switch"] in connected_sws and iface["swport"] in connected_sws[iface["switch"]]:
                    if iface["vlan"]:
                        self.add_vlan(host["name"], iface, 
                                      connected_sws[iface["switch"]][iface["swport"]])


    def add_vlan(self, hostname, iface, port):
        """ Adds a vlan address to the specified port """
        self.vlan_matrix.setdefault(iface["vlan"], [])
        h = self.net.getNodeByName(hostname)
        pname = f"{hostname}-eth{port}"
        vid = iface["vlan"]
        vlan_port_name = f"eth{port}.{vid}"
        host = {"name": hostname}
        h.cmd(f'ip link add link {pname} name {vlan_port_name} type vlan id {vid}')
        if "ipv4" in iface:
            h.cmd(f"ip addr add dev {vlan_port_name} {iface['ipv4']}")
            host["ipv4"] = iface["ipv4"]
        if "ipv6" in iface:
            self.add_ipv6(hostname, vlan_port_name, iface)
            host["ipv6"] = iface["ipv6"]
        self.vlan_matrix[iface["vlan"]].append(host)
        h.cmd(f"ip link set dev {vlan_port_name} up")


    def add_ipv6(self, hostname, portname, iface):
        """ Removes the default ipv6 address from hosts and adds the ip based on
            the hosts matrix """
        h = self.net.getNodeByName(hostname)
        h.cmd(f"ip -6 addr flush dev {portname}")
        h.cmd(f"ip -6 addr add dev {portname} {iface['ipv6']}")

    def pingAllV4(self):
        """ Uses the hosts matrix and pings all the ipv6 addresses, similiar to
            mininet's pingall format """
        output( '*** Ping: testing ping4 reachability\n' )
        packets = 0
        lost = 0
        ploss = None
        for host in self.hosts_matrix:
            h = self.net.getNodeByName(host[0])
            output(f'{host[0]} -> ')
            for dst in self.hosts_matrix:
                if dst is host:
                    continue
                addr6 = dst[1].split('/')[0]
                result = h.cmd(f'ping -c{self.ping_count} -i 0.01 {addr6}')
                # info(result)
                sent, received = self.net._parsePing(result)
                packets += sent
                lost += sent - received
                out = 'X'
                if received:
                    out = dst[0]
                output(f'{out} ')
            output('\n')
        if packets > 0:
                ploss = 100.0 * lost / packets
                received = packets - lost
                output( "*** Results: %i%% dropped (%d/%d received)\n" %
                        ( ploss, received, packets ) )

    def pingAllV6(self):
        """ Uses the hosts matrix and pings all the ipv6 addresses, similar to
            mininet's pingall format """
        output( '*** Ping: testing ping6 reachability\n' )
        packets = 0
        lost = 0
        ploss = None
        for host in self.hosts_matrix:
            h = self.net.getNodeByName(host[0])
            output(f'{host[0]} -> ')
            for dst in self.hosts_matrix:
                if dst is host:
                    continue
                addr6 = dst[2].split('/')[0]
                result = h.cmd(f'ping -c{self.ping_count} -i 0.01 -6 {addr6}')
                # info(result)
                sent, received = self.net._parsePing(result)
                packets += sent
                lost += sent - received
                out = 'X'
                if received:
                    out = dst[0]
                output(f'{out} ')
            output('\n')
        if packets > 0:
                ploss = 100.0 * lost / packets
                received = packets - lost
                output( "*** Results: %i%% dropped (%d/%d received)\n" %
                        ( ploss, received, packets ) )

    def start(self, argv):
        """ Starts the program """
        nw_matrix = None
        args = self.parse_args(argv[1:])
        if args.json:
            error("Direct JSON is not yet supported\n")
            sys.exit()
            # network_matrix = self.parse_json(args.json)
        if args.input:
            nw_matrix = self.open_file(args.input)
        
        if not args.json and not args.input:
            nw_matrix = self.open_file(DEFAULT_INPUT_FILE)
        
        if args.ping:
            try:
                args.ping = int(args.ping)
                self.ping_count = args.ping
            except:
                error('Ping input is not a number, using the default ping count of 1\n')
        
        if not nw_matrix:
            error("No topology discovered. Please check input files\n")

        if nw_matrix:
            self.check_matrix(nw_matrix)
            self.build_network()
            self.net.start()
            self.cleanup_ips()
            
            if (args.cli):
                CLI(self.net)
            else:
                self.test_network()
            self.net.stop()
           
    
    def parse_args(self, sys_args):
        """ Parses the arguments """
        args = argparse.ArgumentParser( 
            prog='mixtt',  
            description='Mininet IXP Topology Tester')
        group =  args.add_mutually_exclusive_group()
        group.add_argument(
            '-j', '--json', 
            action='store', 
            help='topology information as json string')
        group.add_argument(
            '-i', '--input', 
            action='store', 
            help='input file with json topology')
        args.add_argument(
            '-c', '--cli',
            action="store_true",
            help='enables CLI for debugging'
        )
        args.add_argument(
            '-p', '--ping',
            action='store',
            help='set the ping count used for pingalls (default is 1)'
        )
        
        return args.parse_args(sys_args)


    def parse_json(self, json_string):
        """ Parses json string entered through cli """
        data = None
        try:
            data = json.loads(json_string)
        except ValueError as err:
            error(f"Error in the input json string\n")
        return data


    def open_file(self, input_file):
        """ Opens the json file that contains the network topology """
        data = None
        try:
            with open(input_file) as jsonFile:
                data = json.load(jsonFile)
        except (UnicodeDecodeError, PermissionError, ValueError) as err:
            error(f"Error in the file {input_file}\n")
        except FileNotFoundError as err:
            error(f"File not found: {input_file}\n")
            if input_file is DEFAULT_INPUT_FILE:
                error(
                    "Please specify a default topology in " +
                    "/etc/mxitt/topology.json or specify a topology file " +
                    "using the -i --input option\n")
                sys.exit()
        
        return data


    def check_matrix(self, nw_matrix):
        """ Checks and validates the network matrix format """
        err_msg = "Malformed config detected! Please check config: "
        
        if "hosts_matrix" not in nw_matrix:
            error(f"{err_msg}No \"hosts_matrix\" is detected\n")
            sys.exit()
        if not nw_matrix["hosts_matrix"]:
            error(f"{err_msg}hosts_matrix doesn't have content\n")
            sys.exit()
        for host in nw_matrix["hosts_matrix"]:
            malformed = False
            if "name" not in host:
                error(f"{err_msg} Entry detected without a name\n")
                malformed = True
            
            if "interfaces" not in host:
                error(f"{err_msg} Entry detected without any interfaces\n")
                malformed = True
            
            if malformed:
                sys.exit()
            for iface in host["interfaces"]:
                if "ipv4" in iface:
                    if "." not in iface["ipv4"] or "/" not in iface["ipv4"]:
                        error(f"{err_msg}Host: {host['name']} has an error in the ipv4 section\n")
                        error(f"IPv4 section: {iface['ipv4']}\n")
                        malformed = True
                if "ipv6" in iface:
                    if ":" not in iface["ipv6"] or "/" not in iface["ipv6"]:
                        error(f"{err_msg}Host: {host['name']} has an error in ipv6 section\n")
                        error(f"IPv6 section: {iface['ipv6']}\n")
                        malformed = True
                if "ipv4" not in iface and "ipv6" not in iface:
                    error(f"{err_msg}Host: {host['name']} has neither an IPv4 or IPv6 address\n")
                    malformed = True
                if "mac" not in iface:
                    if ":" not in iface["mac"]:
                        error(f"{err_msg}Host: {host['name']} has an error in mac section\n")
                        error(f"mac section: {iface['mac']}\n")
                        malformed = True
                if "mac" not in iface:
                    error(f"{err_msg}Host: {host['name']} does not have a mac address\n")
                    malformed = True
                if "swport" not in iface:
                    error(f"{err_msg}Host: {host['name']} does not have a switch port\n")
                    malformed = True
                if "switch" not in iface:
                    error(f"{err_msg}Host: {host['name']} does not have a switch property\n")
                    malformed = True
                if "vlan" in iface:
                    vid  = int(iface["vlan"])
                    if vid < 0 or vid > 4095:
                        error(f"{err_msg}Host: {host['name']} has an interface" +
                              f"an invalid vlan id. Vid should be between 1" +
                              f" and 4095. Vid :{vid} detected\n")
                if malformed:
                    sys.exit()
            
        if "switch_matrix" not in nw_matrix:
            error(f"{err_msg}No \"switch_matrix\" detected\n")
            sys.exit()
        if not nw_matrix["switch_matrix"]:
            error(f"{err_msg}switch matrix doesn't have content\n")
            sys.exit()
        if "links" not in nw_matrix["switch_matrix"]:
            error(f'{err_msg}switch matrix is missing a links section\n')
            sys.exit()
        
        for switch in nw_matrix["switch_matrix"]["links"]:
            if len(switch) != 4:
                error(f"{err_msg}The switch matrix seems to be missing parts. "+
                "please ensure format is as follows:\n"+
                "[switch1_name,\tport_connecting_switch1_to_switch2,"+
                "\tswitch2_name,\tport_connecting_switch2_to_switch1]\n")
                sys.exit()
        
        if "dp_ids" not in nw_matrix["switch_matrix"]:
            warn("No \"switch_dps\" detected, dps generated in Mininet might" +
            " not match dps in faucet config\n")
        else:
            self.switch_dps = nw_matrix["switch_matrix"]["dp_ids"]

        self.network_matrix = nw_matrix
        self.hosts_matrix = self.network_matrix["hosts_matrix"]
        self.switch_matrix = self.network_matrix["switch_matrix"]["links"]
        


    class MyTopo(Topo):
        "Custom topology generator"
        
        def __init__(self, hosts_matrix=None, switch_matrix=None, switch_dps=None):
            "Create custom topo."

            # Initialize topology
            Topo.__init__(self)
            switch_list = []

            for switch in switch_matrix:
                if switch[0] not in switch_list:
                    switch_list.append(switch[0])
                    if switch_dps and switch[0] in switch_dps:
                        dp_id = switch_dps[switch[0]]
                        self.addSwitch(switch[0], dpid='%x' % dp_id)
                    else:
                        error("No dpid has been found")
                    self.addSwitch(switch[0])
                if switch[2] not in switch_list:
                    switch_list.append(switch[2])
                    if switch_dps and switch[2] in switch_dps:
                        dp_id = switch_dps[switch[2]]
                        self.addSwitch(switch[2], dpid='%x' % dp_id)
                    else:
                        error("No dpid has been found")
                        self.addSwitch(switch[2])
                self.addLink(switch[0], switch[2], int(switch[1]), int(switch[3]))
            
            for host in hosts_matrix:
                self.hostAdd(host)
            

        def hostAdd(self, host):
            """ Adds the host to the network """
            port = 0
            connected_sws = {}
            for iface in host["interfaces"]:
                if iface["switch"] not in connected_sws or \
                   iface["swport"] not in connected_sws[iface["switch"]]:
                    if port is 0:
                        if iface["ipv4"]:
                            h = self.addHost(host["name"], ip=iface["ipv4"], mac=iface["mac"], intf=f"eth-{port}")
                        else:
                            h = self.addHost(host["name"], mac=iface["mac"], intf=f"eth-{port}")
                if iface["switch"] not in connected_sws:
                    connected_sws[iface["switch"]] = {}
                if iface["swport"] not in connected_sws[iface["switch"]]:
                    self.addLink(iface["switch"], host["name"], iface["swport"], port)
                    connected_sws[iface["switch"]][iface["swport"]] = port
                    port+=1


def main():
    setup_logging()
    MIXTT().start(sys.argv)

def setup_logging():
    logname = "mininet"
    logger = logging.getLogger(logname)
    logger_handler = logging.FileHandler(DEFAULT_LOG_FILE)
    log_fmt = '%(asctime)s %(name)-6s %(levelname)-8s %(message)s'
    logger_handler.setFormatter(
        logging.Formatter(log_fmt, '%b %d %H:%M:%S'))
    logger.addHandler(logger_handler)
    logger_handler.setLevel('INFO')
    setLogLevel('info')

if __name__ == '__main__':
    main()
