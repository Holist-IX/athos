#!/usr/bin/python3

""" Mininet IXP Topology tester

Generates a mininet topology based on the info gathered from IXP Manager and the
faucet config generator
"""

from syslog import setlogmask
import mininet.node
import sys
import argparse
import json
import logging
import pdb
from logging import Logger, warning
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel, info, debug, error, warn, output, MininetLogger
from mininet.node import RemoteController
from mininet.cli import CLI
from p4_mininet import P4Switch
from umbrella_scapy import UmbrellaScapy

from sys import argv

DEFAULT_INPUT_FILE = "/etc/mixtt/topology.json"
DEFAULT_LOG_FILE = "/mixtt/ixpman_files/output.txt"
DEFAULT_P4_COMPILER = "p4c"
DEFAULT_P4_OPTIONS = "--target bmv2 --arch"
DEFAULT_P4_SWITCH = "simple_switch"
DEFUALT_UMBRELLA_JSON = "/etc/mixtt/umbrella.json"


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
        self.link_matrix = None
        self.switch_dps = None
        self.vlan_matrix = {}
        self.vlan_to_host_id = []
        self.p4_switches = []
        self.ping_count = 1
        self.no_redundancy = False
        self.thrift_port = 9090
        self.p4_json = DEFUALT_UMBRELLA_JSON


    def build_network(self):
        """ Builds a mininet network based on the network matrix that's been 
            given """

        topo = self.MyTopo( hosts_matrix=self.hosts_matrix, 
                            switch_matrix=self.link_matrix,
                            switch_dps=self.switch_dps,
                            p4_switches=self.p4_switches)
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
        self.ping_vlan_v4()
        self.ping_vlan_v6()
        if self.no_redundancy:
            return
        for link in self.link_matrix:
            s1, s2 = link[0], link[2]
            output(f"Setting link between {s1} and {s2} down\n")
            self.net.configLinkStatus(s1, s2, "down")
            self.ping_vlan_v4()
            self.ping_vlan_v6()
            output(f"Setting link between {s1} and {s2} up\n")
            self.net.configLinkStatus(s1, s2, "up")
            self.ping_vlan_v4()
            self.ping_vlan_v6()


    def cleanup_ips(self):
        """ Cleans up ip addresses, in particular hosts with multiple interfaces
            and vlans """
        
        self.vlan_matrix["none"] = []
        for iface in self.hosts_matrix:
            h = {"name": iface["name"]}
            h["port"] = f"h{iface['id']}-eth0"
            h["id"] = iface["id"]
            if "ipv4" in iface:
                h["ipv4"] = iface["ipv4"]
            if "ipv6" in iface:
                h["ipv6"] = iface["ipv6"]
                self.add_ipv6(iface['id'], f"h{iface['id']}-eth0", iface)
            if "vlan" not in iface:
                self.vlan_matrix["none"].append(h)
        for iface in self.vlan_to_host_id:
            h = {"name": iface["name"]}
            h["port"] = "eth-0"
            if "ipv4" in iface:
                h["ipv4"] = iface["ipv4"]
            if "ipv6" in iface:
                h["ipv6"] = iface["ipv6"]
            hnode = self.net.getNodeByName(f"h{iface['id']}")
            if hnode.IP() == "127.0.0.1":
                hnode.cmd(f"ip addr del dev h{iface['id']}-eth0 127.0.0.1")
                hnode.cmd(f"ip -6 addr flush dev h{iface['id']}-eth0")
            hnode.cmd(f"ip link set dev h{iface['id']}-eth0 {iface['mac']}")
            self.add_vlan(iface["id"], iface, 0)


    def add_vlan(self, hostname, iface, port):
        """ Adds a vlan address to the specified port """
        self.vlan_matrix.setdefault(iface["vlan"], [])
        h = self.net.getNodeByName(f"h{hostname}")
        pname = f"h{hostname}-eth{port}"
        vid = iface["vlan"]
        vlan_port_name = f"eth{port}.{vid}"
        host = {"name": iface["name"]}
        host["port"] = vlan_port_name
        host["id"] = iface["id"]
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
        h = self.net.getNodeByName(f"h{hostname}")
        h.cmd(f"ip -6 addr flush dev {portname}")
        h.cmd(f"ip -6 addr add dev {portname} {iface['ipv6']}")

    def ping_vlan_v4(self):
        """ Uses the hosts matrix and pings all the ipv6 addresses, similar to
            mininet's pingall format """
        output( '*** Ping: testing ping4 reachability\n' )
        packets = 0
        lost = 0
        ploss = None
        for vlan in self.vlan_matrix:
            output(f"Testing reachability for hosts with vlan: {vlan}\n")
            for host in self.vlan_matrix[vlan]:
                h = self.net.getNodeByName(f"h{host['id']}")
                output(f'{host["name"]} -> ')
                for dst in self.vlan_matrix[vlan]:
                    if dst is host:
                        continue
                    if "ipv4" not in host:
                        continue
                    addr = dst['ipv4'].split('/')[0]
                    result = h.cmd(f'ping -I {host["port"]} -c{self.ping_count} -i 0.01 {addr}')
                    # info(result)
                    sent, received = self.net._parsePing(result)
                    packets += sent
                    lost += sent - received
                    out = 'X'
                    if received:
                        out = dst["name"]
                    output(f'{out} ')
                output('\n')
        if packets > 0:
            ploss = 100.0 * lost / packets
            received = packets - lost
            output( "*** Results: %i%% dropped (%d/%d received)\n" % 
                  ( ploss, received, packets ) )

    
    def ping_vlan_v6(self):
        """ Uses the hosts matrix and pings all the ipv6 addresses, similar to
            mininet's pingall format """
        output( '*** Ping: testing ping6 reachability\n' )
        packets = 0
        lost = 0
        ploss = None
        for vlan in self.vlan_matrix:
            output(f"Testing reachability for hosts with vlan: {vlan}\n")
            for host in self.vlan_matrix[vlan]:
                h = self.net.getNodeByName(f"h{host['id']}")
                output(f'{host["name"]} -> ')
                for dst in self.vlan_matrix[vlan]:
                    if dst is host:
                        continue
                    if "ipv6" not in host:
                        continue
                    addr = dst['ipv6'].split('/')[0]
                    result = h.cmd(f'ping -I {host["port"]} -c{self.ping_count} -i 0.01 -6 {addr}')
                    # info(result)
                    sent, received = self.net._parsePing(result)
                    packets += sent
                    lost += sent - received
                    out = 'X'
                    if received:
                        out = dst["name"]
                    output(f'{out} ')
                output('\n')
        if packets > 0:
            ploss = 100.0 * lost / packets
            received = packets - lost
            output( "*** Results: %i%% dropped (%d/%d received)\n" % 
                  ( ploss, received, packets ) )
                        
    # Possibly redundant code, keeping for testing purpose
    def pingAllV4(self):
        """ Uses the hosts matrix and pings all the ipv6 addresses, similar to
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

    
    # Possibly redundant code, keeping for testing purpose
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
        setLogLevel('info')
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

        if args.thrift_port:
            self.thrift_port = args.thrift_port

        if args.no_redundancy:
            self.no_redundancy = True
            output('No redundancy testing mode\n')

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
            help='Topology information as json string')
        group.add_argument(
            '-i', '--input', 
            action='store', 
            help='Input file with json topology')
        args.add_argument(
            '-c', '--cli',
            action="store_true",
            help='Enables CLI for debugging'
        )
        args.add_argument(
            '-p', '--ping',
            action='store',
            help='Set the ping count used for pingalls (default is 1)'
        )
        args.add_argument(
            '-n', '--no-redundancy',
            action='store_true',
            help='Disables the link redundancy checker'
        )
        args.add_argument(
            '-t', '--thrift-port',
            action="store",
            help="Thrift server port for p4 table updates",
            default="9090"
        )
        args.add_argument(
            '--p4-json',
            action='store',
            help="Config json for p4 switches"
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
                    mac = ""
                    for other_iface in host["interfaces"]:
                        if iface is other_iface:
                            continue

                        if not malformed and \
                           iface["switch"] == other_iface["switch"] and \
                           iface["swport"] == other_iface["swport"] and \
                           "mac" in other_iface:

                            mac = other_iface["mac"]
                            iface["mac"] = mac
                    
                    if not mac:
                        error(f"{err_msg}Host: {host['name']} does not have a mac address\n")
                        malformed = True
                
                if "mac" in iface:
                    if ":" not in iface["mac"]:
                        error(f"{err_msg}Host: {host['name']} has an error in mac section\n")
                        error(f"mac section: {iface['mac']}\n")
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

        if "p4" in nw_matrix["switch_matrix"]:
            self.p4_switches = nw_matrix["switch_matrix"]["p4"]
        self.hosts_matrix = self.flatten_nw_matrix(nw_matrix)
        self.link_matrix = nw_matrix["switch_matrix"]["links"]
        

    def flatten_nw_matrix(self, nw_matrix):
        """ Flattens out the topology matrix turning each interface into a 
            separate namespace """
        flattened_matrix = []
        id = 1
        for host in nw_matrix["hosts_matrix"]:
            hname = host["name"]
            connected_sw = {}
            ifaces = []
            vlan_ifaces = []
            untagged_ids = []
            tagged_ids = []
            for iface in host["interfaces"]:
                switch = iface["switch"]
                swport = iface["swport"]
                if switch not in connected_sw:
                    connected_sw[switch] = {swport:id}
                    h = iface
                    h["name"] = hname
                    h["id"] = id
                    if "vlan" not in iface:
                        ifaces.append(h)
                        untagged_ids.append(id)
                    else:
                        vlan_ifaces.append(h)
                        tagged_ids.append(id)
                    id+=1
                    continue
                if swport not in connected_sw[switch]:
                    connected_sw[switch][swport] = id
                    h = iface
                    h["name"] = hname
                    h["id"] = id
                    if "vlan" not in iface:
                        ifaces.append(h)
                        untagged_ids.append(id)
                    else:
                        vlan_ifaces.append(h)
                        tagged_ids.append(id)
                    id+=1
                    continue

                tempid = connected_sw[switch][swport]
                h = iface
                h["name"] = hname
                h["id"] = tempid
                if "vlan" not in iface:
                    ifaces.append(h)
                    untagged_ids.append(tempid)
                else:
                    vlan_ifaces.append(h)
                    tagged_ids.append(tempid)
                id+=1
                continue
                
            for iface in vlan_ifaces:
                if iface["id"] not in untagged_ids:
                    # To prevent interference with multiple vlans on same iface
                    untagged_ids.append(iface["id"])
                    ifaces.append(iface)
            self.vlan_to_host_id.extend(vlan_ifaces)
            flattened_matrix.extend(ifaces)
        
        return flattened_matrix


    class MyTopo(Topo):
        """ Custom topology generator """
        
        def __init__(self, hosts_matrix=None, switch_matrix=None, 
                     switch_dps=None, p4_switches=None,
                     sw_path=DEFAULT_P4_SWITCH,
                     p4_json=DEFUALT_UMBRELLA_JSON):
            """ Create a topology based on input JSON"""

            # Initialize topology
            Topo.__init__(self)
            switch_list = []

            for sw in switch_dps:
                dp_id = switch_dps[sw]
                switch_list.append(sw)
                self.addSwitch(sw, dpid='%x' % dp_id)
            if p4_switches:
                output('Adding p4 switches:\t')
                for sw in p4_switches:
                    output(f'{sw}\t')
                    # TODO: Change to variables
                    self.addSwitch(sw, cls=P4Switch, 
                                   sw_path= "simple_switch",
                                   json_path=DEFUALT_UMBRELLA_JSON,
                                   thrift_port=9090
                                   )
                    switch_list.append(sw)
                output('\n')
            for switch in switch_matrix:
                self.addLink(switch[0], switch[2], 
                             int(switch[1]), int(switch[3]))
            
            for host in hosts_matrix:
                self.hostAdd(host)
            

        def hostAdd(self, host):
            """ Adds the host to the network """
            hname = f"h{host['id']}"
            if "ipv4" in host and "vlan" not in host:
                self.addHost(hname, ip=host["ipv4"], mac=host["mac"],
                             intf="eth-0")
            else:
                self.addHost(hname, ip="127.0.0.1/32", mac=host["mac"],
                                  intf="eth-0")
            self.addLink(host["switch"], hname, host["swport"])
