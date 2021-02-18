#!/usr/bin/python3

""" Mininet IXP Topology tester

Generates a mininet topology based on the info gathered from IXP Manager and the
faucet config generator
"""

import sys
import json
import time
from datetime import datetime
from subprocess import call
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import output, info, error, warn
from mixtt.p4_mininet import P4Switch


DEFAULT_INPUT_FILE = "/etc/mixtt/topology.json"
DEFAULT_P4_COMPILER = "p4c"
DEFAULT_P4_OPTIONS = "--target bmv2 --arch"
DEFAULT_P4_SWITCH = "simple_switch"
DEFAULT_UMBRELLA_JSON = "/etc/mixtt/umbrella.json"
DEFAULT_LOG_FILE = "/var/log/mixtt/mixtt.log"

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
        self.logger = None


    def build_network(self, thrift_port_base=9190):
        """ Builds a mininet network based on the network matrix that's been
            given """

        topo = self.MyTopo(hosts_matrix=self.hosts_matrix,
                           switch_matrix=self.link_matrix,
                           switch_dps=self.switch_dps,
                           p4_switches=self.p4_switches,
                           logger=self.logger,
                           thrift_port_base=thrift_port_base)
        self.net = Mininet(
            topo=topo,
            controller=RemoteController(
                name="faucet",
                ip="127.0.0.1",
                port=6653
            ))


    def test_network(self, no_redundancy=False, ping_count=1):
        """ Sets up the network and tests that all hosts can ping each other in
            ipv4 and ipv6. Also tests failover by disabling links between
            switches """
        self.ping_vlan_v4(ping_count)
        # Compensates for ipv6 taking some time to set up
        time.sleep(1)
        self.ping_vlan_v6(ping_count)
        # No redundancy mode until p4 redundancy has been tested more
        if no_redundancy or self.p4_switches:
            return
        for link in self.link_matrix:
            source_switch, destination_switch = link[0], link[2]
            self.log_info(f"Setting link between {source_switch}  " +
                          f"and {destination_switch} down")
            self.net.configLinkStatus(source_switch, destination_switch, "down")
            self.ping_vlan_v4(ping_count)
            self.ping_vlan_v6(ping_count)
            self.log_info(f"Setting link between {source_switch} " +
                          f"and {destination_switch} up")
            self.net.configLinkStatus(source_switch, destination_switch, "up")
            self.ping_vlan_v4(ping_count)
            self.ping_vlan_v6(ping_count)


    def cleanup_ips(self):
        """ Cleans up ip addresses, in particular hosts with multiple interfaces
            and vlans """
        self.vlan_matrix["none"] = []
        for iface in self.hosts_matrix:
            host = {"name": iface["name"]}
            host["port"] = f"h{iface['id']}-eth0"
            host["id"] = iface["id"]
            if "ipv4" in iface:
                host["ipv4"] = iface["ipv4"]
            if "ipv6" in iface:
                host["ipv6"] = iface["ipv6"]
                self.add_ipv6(iface['id'], f"h{iface['id']}-eth0", iface)
            if "vlan" not in iface:
                self.vlan_matrix["none"].append(host)
        for iface in self.vlan_to_host_id:
            host = {"name": iface["name"]}
            host["port"] = "eth-0"
            if "ipv4" in iface:
                host["ipv4"] = iface["ipv4"]
            if "ipv6" in iface:
                host["ipv6"] = iface["ipv6"]
            hnode = self.net.getNodeByName(f"h{iface['id']}")
            if hnode.IP() == "127.0.0.1":
                hnode.cmd(f"ip addr del dev h{iface['id']}-eth0 127.0.0.1")
                hnode.cmd(f"ip -6 addr flush dev h{iface['id']}-eth0")
            hnode.cmd(f"ip link set dev h{iface['id']}-eth0 {iface['mac']}")
            self.add_vlan(iface["id"], iface, 0)


    def add_vlan(self, hostname, iface, port):
        """ Adds a vlan address to the specified port """
        self.vlan_matrix.setdefault(iface["vlan"], [])
        host_node = self.net.getNodeByName(f"h{hostname}")
        phase = f"h{hostname}-eth{port}"
        vid = iface["vlan"]
        vlan_port_name = f"eth{port}.{vid}"
        host = {"name": iface["name"]}
        host["port"] = vlan_port_name
        host["id"] = iface["id"]
        host_node.cmd(f'ip link add link {phase} name ' +
                      f'{vlan_port_name} type vlan id {vid}')
        if "ipv4" in iface:
            host_node.cmd(f"ip addr add dev {vlan_port_name} {iface['ipv4']}")
            host["ipv4"] = iface["ipv4"]
        if "ipv6" in iface:
            self.add_ipv6(hostname, vlan_port_name, iface)
            host["ipv6"] = iface["ipv6"]
        self.vlan_matrix[iface["vlan"]].append(host)
        host_node.cmd(f"ip link set dev {vlan_port_name} up")


    def add_ipv6(self, hostname, portname, iface):
        """ Removes the default ipv6 address from hosts and adds the ip based on
            the hosts matrix """
        host_node = self.net.getNodeByName(f"h{hostname}")
        host_node.cmd(f"ip -6 addr flush dev {portname}")
        host_node.cmd(f"ip -6 addr add dev {portname} {iface['ipv6']}")

    def ping_vlan_v4(self, ping_count=1):
        """ Uses the hosts matrix and pings all the ipv6 addresses, similar to
            mininet's pingall format """
        self.log_info('*** Ping: testing ping4 reachability')
        packets = 0
        lost = 0
        ploss = None
        for vlan in self.vlan_matrix:
            self.log_info(f"Testing reachability for hosts with vlan: {vlan}")
            for host in self.vlan_matrix[vlan]:
                results = []
                host_node = self.net.getNodeByName(f"h{host['id']}")
                self.to_console(f'{host["name"]} -> ')
                for dst in self.vlan_matrix[vlan]:
                    if dst is host:
                        continue
                    if "ipv4" not in host:
                        continue
                    addr = dst['ipv4'].split('/')[0]
                    result = host_node.cmd(f'ping -I {host["port"]}' +
                                           f' -c{ping_count} -i 0.01 {addr}')
                    self.logger.debug(result)
                    sent, received = self.net._parsePing(result)
                    packets += sent
                    lost += sent - received
                    out = 'X'
                    if received:
                        out = dst["name"]
                    self.to_console(f'{out} ')
                    results.append(out)
                output('\n')
        if packets > 0:
            ploss = 100.0 * lost / packets
            received = packets - lost
            self.log_info("*** Results: %i%% dropped (%d/%d received)" %
                          (ploss, received, packets))


    def ping_vlan_v6(self, ping_count=1):
        """ Uses the hosts matrix and pings all the ipv6 addresses, similar to
            mininet's pingall format """
        self.log_info('*** Ping: testing ping6 reachability')
        packets = 0
        lost = 0
        ploss = None
        for vlan in self.vlan_matrix:
            self.log_info(f"Testing reachability for hosts with vlan: {vlan}")
            for host in self.vlan_matrix[vlan]:
                host_node = self.net.getNodeByName(f"h{host['id']}")
                output(f'{host["name"]} -> ')
                for dst in self.vlan_matrix[vlan]:
                    if dst is host:
                        continue
                    if "ipv6" not in host:
                        continue
                    addr = dst['ipv6'].split('/')[0]
                    result = host_node.cmd(f'ping6 -I {host["port"]}' +
                                           f' -c{ping_count}' +
                                           f' -i 0.01 {addr}')
                    self.logger.debug(result)
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
            self.log_info("*** Results: %i%% dropped (%d/%d received)" %
                          (ploss, received, packets))


    def start(self, args, logger):
        """ Starts the program """

        self.logger = logger
        ping_count = 1

        info(f"{datetime.now().strftime('%b %d %H:%M:%S')}\n")
        info('Starting new Testing instance\n')
        nw_matrix = None
        if args.json_topology:
            self.log_error("Direct JSON is not yet supported")
            sys.exit()
        if args.topology_file:
            nw_matrix = self.open_file(args.topology_file)

        if not args.json_topology and not args.topology_file:
            nw_matrix = self.open_file(DEFAULT_INPUT_FILE)

        if not nw_matrix:
            self.log_error("No topology discovered. Please check input files")

        try:
            ping_count = int(args.ping)
        except TypeError as err:
            self.log_error('Ping input is not a number,' +
                           f' using the default ping count of 1\n{err}')

        t_port = None
        if args.thrift_port:
            t_port = args.thrift_port

        if nw_matrix:
            self.parse_config(nw_matrix)
            self.build_network(t_port)
            self.net.start()
            self.cleanup_ips()

            if args.script:
                MIXTT.run_start_script(args.script)

            if args.cli:
                CLI(self.net)
            else:
                self.test_network(args.no_redundancy, ping_count)
            self.net.stop()


    def parse_json(self, json_string):
        """ Parses json string entered through cli """
        data = None
        try:
            data = json.loads(json_string)
        except ValueError as err:
            self.log_error(f"Error in the input json string\n{err}")
        return data


    def open_file(self, input_file):
        """ Opens the json file that contains the network topology """
        data = None
        try:
            with open(input_file) as json_file:
                data = json.load(json_file)
        except (UnicodeDecodeError, PermissionError, ValueError) as err:
            self.log_error(f"Error in the file {input_file}\n{err}")
        except FileNotFoundError as err:
            self.log_error(f"File not found: {input_file}\n")
            if input_file is DEFAULT_INPUT_FILE:
                self.log_error(
                    "Please specify a default topology in " +
                    "/etc/mxitt/topology.json or specify a topology file " +
                    f"using the -i --input option\n{err}")
                sys.exit()

        return data

    @staticmethod
    def run_start_script(script):
        """ Runs specified startup script before continuing. Typical use cases
            would be starting controllers or loading switches with rules """
        call(script, shell=True)


    def parse_config(self, nw_matrix):
        """ Parses and validates the config """
        err_msg = "Malformed config detected!"
        try:
            if "hosts_matrix" not in nw_matrix:
                raise ConfigError(f"{err_msg}No 'hosts_matrix' found\n")
            if "switch_matrix" not in nw_matrix:
                raise ConfigError(f"{err_msg}No 'hosts_matrix' found\n")
        except ConfigError as err:
            self.log_error(err)
            sys.exit()
        self.check_hosts_config(nw_matrix["hosts_matrix"])
        self.check_switch_config(nw_matrix["switch_matrix"])
        self.hosts_matrix = self.flatten_nw_matrix(nw_matrix)


    def check_hosts_config(self, host_matrix):
        """ Parses and validates the hosts matrix """
        err_msg = ("Malformed config detected in the hosts section!\n" +
                   "Please check the config:\n")
        if not host_matrix:
            self.log_error(f"{err_msg} hosts_matrix doesn't have any content\n")

        for host in host_matrix:
            malformed = False
            if "name" not in host:
                self.log_error(f"{err_msg} Entry detected without a name\n")
                malformed = True

            if "interfaces" not in host:
                self.log_error(f"{err_msg} Entry detected " +
                               "without any interfaces\n")
                malformed = True
            if malformed:
                sys.exit()

            self.check_host_interfaces(err_msg, host)


    def check_host_interfaces(self, err_msg, host):
        """ Parse and validates the host's interfaces """
        err_msg = err_msg + f"Host: {host['name']} has an error"

        try:
            if not host["interfaces"]:
                raise ConfigError(f"{err_msg} interfaces section is empty")

            for iface in host["interfaces"]:
                if "swport" not in iface:
                    raise ConfigError(f"{err_msg}. It does not have a " +
                                      "switch port\n")
                if "switch" not in iface:
                    raise ConfigError(f"{err_msg}. It does not have an " +
                                      "assigned switch\n")
                if "ipv4" in iface:
                    self.check_ipv4_address(err_msg, iface["ipv4"])
                if "ipv6" in iface:
                    self.check_ipv6_address(err_msg, iface["ipv6"])
                if "ipv4" not in iface and "ipv6" not in iface:
                    raise ConfigError(f"{err_msg}. It has neither an IPv4" +
                                      " or IPv6 address\n")
                if "mac" not in iface:
                    iface["mac"] = \
                        self.check_for_available_mac(err_msg, iface,
                                                     host["interfaces"])
                if "mac" in iface:
                    self.check_mac_address(err_msg, iface["mac"])
                if "vlan" in iface:
                    self.check_vlan_validity(err_msg, iface["vlan"])

        except ConfigError as err:
            self.log_error(err)
            sys.exit()

    def check_ipv4_address(self, err_msg, v4_address):
        """ Checks validity of ipv4 address """
        try:
            if not v4_address:
                raise ConfigError(f"{err_msg} please check that ipv4 sections" +
                                  "have addresses assigned")
            if "." not in v4_address or "/" not in v4_address:
                raise ConfigError(f"{err_msg} in the ipv4 section\n" +
                                  f"IPv4 section: {v4_address}\n")
        except ConfigError as err:
            self.log_error(err)
            sys.exit()


    def check_ipv6_address(self, err_msg, v6_address):
        """ Checks validity of ipv6 address """
        try:
            if not v6_address:
                raise ConfigError(f"{err_msg} please check that ipv6 sections" +
                                  "have addresses assigned")
            if ":" not in v6_address or "/" not in v6_address:
                raise ConfigError(f"{err_msg} in the ipv6 section\n" +
                                  f"IPv6 section: {v6_address}\n")
        except ConfigError as err:
            self.log_error(err)
            sys.exit()


    def check_mac_address(self, err_msg, mac_address):
        """ Checks validity of MAC address """
        try:
            if not mac_address:
                raise ConfigError(f"{err_msg} please check that MAC sections" +
                                  "have addresses assigned")
            if ":" not in mac_address:
                raise ConfigError(f"{err_msg} in the MAC section. Currently " +
                                  "only : seperated addresses are supported\n" +
                                  f"MAC section: {mac_address}\n")
        except ConfigError as err:
            self.log_error(err)
            sys.exit()


    def check_for_available_mac(self, err_msg, iface, host_interfaces):
        """ Checks if port another mac address is assigned to the port """
        mac = ""
        try:
            for other_iface in host_interfaces:
                if iface is other_iface:
                    continue

                if iface["switch"] == other_iface["switch"] and \
                iface["swport"] == other_iface["swport"] and \
                "mac" in other_iface:

                    mac = other_iface["mac"]

            if not mac:
                raise ConfigError(f"{err_msg} in the mac section. " +
                                  "No mac address was provided")
        except ConfigError as err:
            self.log_error(err)

        return mac


    def check_vlan_validity(self, err_msg, vlan):
        """ Checks that the assigned vlan is a valid value """
        try:
            vid = int(vlan)
            if vid < 0 or vid > 4095:
                raise ConfigError(f"{err_msg}. Invalid vlan id(vid) detected" +
                                  "Vid should be between 1 and 4095. " +
                                  f"Vid: {vid} detected\n")
        except (ConfigError, ValueError) as err:
            self.log_error(err)
            sys.exit()


    def check_switch_config(self, sw_matrix):
        """ Parses and validates the switch matrix """
        err_msg = ("Malformed config detected in the switch section!\n" +
                   "Please check the config:\n")
        try:
            if not sw_matrix:
                raise ConfigError(f"{err_msg}Switch matrix is empty")
            if "links" not in sw_matrix:
                raise ConfigError(f"{err_msg}No links section found")
            for link in sw_matrix["links"]:
                if len(link) != 4:
                    raise ConfigError(f"{err_msg}Invalid link found."+
                                      "Expected link format:\n"
                                      "[switch1_name,a,swithch2_name,b]\n" +
                                      "Where a is the port on switch1 " +
                                      "connected to switch2, and vice versa " +
                                      f"for b\nLink found: {link}")
                port_a = int(link[1])
                port_b = int(link[3])

                if port_a < 0 or port_a > 255 or port_b < 0 or port_b > 255:
                    raise ConfigError("Invalid port number detected. Ensure" +
                                      "that port numbers are between 0 and 255"+
                                      f"sw1_port: {port_a}\t sw2_port:{port_b}")
            if "dp_ids" not in sw_matrix:
                self.log_warn(f"{err_msg}No dp_id section found, dp_ids " +
                              "generated in Mininet might not match those in " +
                              "controller config")
            else:
                for _, dp_id in sw_matrix["dp_ids"]:
                    if not dp_id.isnumeric():
                        raise ConfigError(f"{err_msg}Please ensure that" +
                                          " dp_ids are valid numbers")
                self.switch_dps = sw_matrix["dp_ids"]
            if "p4" in sw_matrix:
                self.p4_switches = sw_matrix["p4"]
            self.link_matrix = sw_matrix["links"]

        except ConfigError as err:
            self.log_error(err)
            sys.exit()
        except ValueError as err:
            self.log_error(f"{err_msg} Please check value of port numbers")
            self.log_error(err)
            sys.exit()


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
                    id += 1
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
                    id += 1
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
                id += 1
                continue

            for iface in vlan_ifaces:
                if iface["id"] not in untagged_ids:
                    # To prevent interference with multiple vlans on same iface
                    untagged_ids.append(iface["id"])
                    ifaces.append(iface)
            self.vlan_to_host_id.extend(vlan_ifaces)
            flattened_matrix.extend(ifaces)

        return flattened_matrix


    @staticmethod
    def to_console(message):
        """ Outputs log message to console """
        output(message)

    def log_info(self, message):
        """ Workaround to make mininet logger work with normal logger """
        info(f'{message}\n')
        self.logger.info(message)

    def log_error(self, message):
        """ Workaround to make mininet logger work with normal logger """
        error(f'{message}\n')
        self.logger.error('message')

    def log_warn(self, message):
        """ Workaround to make mininet logger work with normal logger """
        warn(f'{message}\n')
        self.logger.warning('message')

    class MyTopo(Topo):
        """ Custom topology generator """

        def __init__(self, hosts_matrix=None, switch_matrix=None,
                     switch_dps=None, p4_switches=None,
                     sw_path=DEFAULT_P4_SWITCH,
                     p4_json=DEFAULT_UMBRELLA_JSON,
                     logger=None,
                     thrift_port_base=9190):
            """ Create a topology based on input JSON"""

            # Initialize topology
            Topo.__init__(self)
            switch_list = []
            self.logger = logger

            for sw in switch_dps:
                dp_id = switch_dps[sw]
                switch_list.append(sw)
                self.addSwitch(sw, dpid='%x' % dp_id)
            if p4_switches:
                self.log_info('Adding p4 switches:')
                i = 0
                for sw in p4_switches:
                    self.log_info(f'{sw}')
                    # Need to allow for multiple p4 switches to be used
                    # Can't use 9090 due to promethues clash
                    t_port = int(thrift_port_base) + int(i)
                    i += 1
                    self.addSwitch(sw, cls=P4Switch,
                                   sw_path=sw_path,
                                   json_path=p4_json,
                                   thrift_port=t_port
                                   )
                    switch_list.append(sw)
            for switch in switch_matrix:
                self.addLink(switch[0], switch[2],
                             int(switch[1]), int(switch[3]))

            for host in hosts_matrix:
                self.host_add(host)


        def host_add(self, host):
            """ Adds the host to the network """
            hname = f"h{host['id']}"
            if "ipv4" in host and "vlan" not in host:
                self.addHost(hname, ip=host["ipv4"], mac=host["mac"],
                             intf="eth-0")
            else:
                self.addHost(hname, ip="127.0.0.1/32", mac=host["mac"],
                             intf="eth-0")
            self.addLink(host["switch"], hname, host["swport"])

        @staticmethod
        def to_console(message):
            """ Outputs log message to console """
            output(message)

        def log_info(self, message):
            """ Workaround to make mininet logger work with normal logger """
            info(f'{message}\n')
            self.logger.info(message)

        def log_error(self, message):
            """ Workaround to make mininet logger work with normal logger """
            error(f'{message}\n')
            self.logger.error('message')

class ConfigError(Exception):
    """ Exception handler for misconfigured configurations """
    pass
