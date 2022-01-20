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
from athos.p4_mininet import P4Switch


DEFAULT_INPUT_FILE = "/etc/athos/topology.json"
DEFAULT_P4_COMPILER = "p4c"
DEFAULT_P4_OPTIONS = "--target bmv2 --arch"
DEFAULT_P4_SWITCH = "simple_switch"
DEFAULT_UMBRELLA_JSON = "/etc/athos/umbrella.json"
DEFAULT_LOG_FILE = "/var/log/athos/athos.log"
DEFAULT_PLOSS_THRESHOLD = 5 # Threshold in % of packet loss before stopping test

LOGMSGFORMAT = '%(message)s'

class ATHOS():
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
        self.unmanaged_switches = []
        self.ploss_threshold = DEFAULT_PLOSS_THRESHOLD


    def build_network(self, thrift_port_base=9190):
        """ Builds a mininet network based on the network matrix that's been
            given """

        topo = self.MyTopo(hosts_matrix=self.hosts_matrix,
                           switch_matrix=self.link_matrix,
                           switch_dps=self.switch_dps,
                           p4_switches=self.p4_switches,
                           unmanaged_switches=self.unmanaged_switches,
                           logger=self.logger,
                           thrift_port_base=thrift_port_base)
        self.net = Mininet(
            topo=topo,
            controller=RemoteController(
                name="cerberus-controller",
                ip="127.0.0.1",
                port=6653
            ))


    def test_network(self, no_redundancy=False, ping_count=1):
        """ Sets up the network and tests that all hosts can ping each other in
            ipv4 and ipv6. Also tests failover by disabling links between
            switches """
        v4_loss = self.ping_vlan_v4(ping_count)
        # Compensates for ipv6 taking some time to set up
        time.sleep(1)
        v6_loss = self.ping_vlan_v6(ping_count)
        ploss_passed = self.packet_loss_threshold_passed(v4_loss, v6_loss)
        if not ploss_passed:
            return
        # No redundancy mode until p4 redundancy has been tested more
        if no_redundancy or self.p4_switches:
            return
        for link in (l for l in self.link_matrix if self.backup_exists(l)):
            source_switch, destination_switch = link[0], link[2]
            info(f"Setting link between {source_switch} and "
                 f"{destination_switch} down\n")
            self.net.configLinkStatus(source_switch, destination_switch, "down")
            self.ping_vlan_v4(ping_count)
            self.ping_vlan_v6(ping_count)
            ploss_passed = self.packet_loss_threshold_passed(v4_loss, v6_loss,
                                    source_switch, destination_switch, "down")
            if not ploss_passed:
                return
            info(f"Setting link between {source_switch} and "
                 f"{destination_switch} up\n")
            self.net.configLinkStatus(source_switch, destination_switch, "up")
            self.ping_vlan_v4(ping_count)
            self.ping_vlan_v6(ping_count)
            ploss_passed = self.packet_loss_threshold_passed(v4_loss, v6_loss,
                                    source_switch, destination_switch, "up")
            if not ploss_passed:
                return


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
        vlan_port_name = f"eth{port}.{vid}" if iface['tagged'] else f'h{iface["id"]}-eth0'
        host = {"name": iface["name"]}
        host["port"] = vlan_port_name
        host["id"] = iface["id"]
        if iface["tagged"]:
            host_node.cmd(f'ip link add link {phase} name ' +
                        f'{vlan_port_name} type vlan id {vid}')
        if "ipv4" in iface:
            host_node.cmd(f"ip addr add dev {vlan_port_name} {iface['ipv4']}")
            host["ipv4"] = iface["ipv4"]
        if "ipv6" in iface:
            self.add_ipv6(hostname, vlan_port_name, iface)
            host["ipv6"] = iface["ipv6"]
        if iface["tagged"]:
            host_node.cmd(f"ip link set dev {vlan_port_name} up")
            host_node.cmd(f"ip link set address {iface['mac']} dev {vlan_port_name}")
        self.vlan_matrix[iface["vlan"]].append(host)


    def add_ipv6(self, hostname, portname, iface):
        """ Removes the default ipv6 address from hosts and adds the ip based on
            the hosts matrix """
        host_node = self.net.getNodeByName(f"h{hostname}")
        host_node.cmd(f"ip -6 addr flush dev {portname}")
        host_node.cmd(f"ip -6 addr add dev {portname} {iface['ipv6']}")

    def ping_vlan_v4(self, ping_count=1):
        """ Uses the hosts matrix and pings all the ipv6 addresses, similar to
            mininet's pingall format """
        info('*** Ping: testing ping4 reachability\n')
        packets = 0
        lost = 0
        ploss = None
        for vlan in self.vlan_matrix:
            info(f"Testing reachability for hosts with vlan: {vlan}\n")
            for host in self.vlan_matrix[vlan]:
                results = []
                if "ipv4" not in host:
                    continue
                host_node = self.net.getNodeByName(f"h{host['id']}")
                output(f'{host["name"]} -> ')
                for dst in self.vlan_matrix[vlan]:
                    if dst is host:
                        continue
                    if "ipv4" not in dst:
                        continue
                    addr = dst['ipv4'].split('/')[0]
                    result = host_node.cmd(f'ping -I {host["port"]}' +
                                           f' -c{ping_count}  -W 1 -i 0.01 {addr}')
                    self.logger.debug(result)
                    sent, received = self.net._parsePing(result)
                    packets += sent
                    lost += sent - received
                    out = 'X'
                    if received:
                        out = dst["name"]
                    output(f'{out} ')
                    results.append(out)
                output('\n')
        if packets > 0:
            ploss = 100.0 * lost / packets
            received = packets - lost
            info(f"*** Results: {round(ploss, 2)}% dropped "
                 f"({received}/{packets} received)\n")
            return ploss


    def ping_vlan_v6(self, ping_count=1):
        """ Uses the hosts matrix and pings all the ipv6 addresses, similar to
            mininet's pingall format """
        info('*** Ping: testing ping6 reachability\n')
        packets = 0
        lost = 0
        ploss = None
        for vlan in self.vlan_matrix:
            info(f"Testing reachability for hosts with vlan: {vlan}\n")
            for host in self.vlan_matrix[vlan]:
                if "ipv6" not in host:
                    continue
                host_node = self.net.getNodeByName(f"h{host['id']}")
                output(f'{host["name"]} -> ')
                for dst in self.vlan_matrix[vlan]:
                    if dst is host:
                        continue
                    if "ipv6" not in dst:
                        continue
                    addr = dst['ipv6'].split('/')[0]
                    result = host_node.cmd(
                        f'ping6 -I {host["port"]} -c{ping_count} -W 1 -i 0.01 {addr}')
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
            info(f"*** Results: {round(ploss, 2)}% dropped "
                 f"({received}/{packets} received)\n")
            return ploss


    def backup_exists(self, link):
        """ Checks if the switches have a redundant path setup """
        src_switch, dst_switch = link[0], link[2]

        src_has_other_link = False
        dst_has_other_link = False

        for l in (i for i in self.link_matrix if i != link):
            src_has_other_link = True if src_switch in l else src_has_other_link
            dst_has_other_link = True if dst_switch in l else dst_has_other_link

        if not src_has_other_link:
            warn(f"Warning: {src_switch} does not have another core link, the "
                 f"link between {src_switch} and {dst_switch} will not be "
                 f"turned off\n")
            return False
        if not dst_has_other_link:
            warn(f"Warning: {dst_switch} does not have another core link, the "
                 f"link between {dst_switch} and {src_switch} will not be "
                 f"turned off\n")
            return False
        return True


    def start(self, args, logger):
        """ Starts the program """

        self.logger = logger
        ping_count = 1

        info(f"{datetime.now().strftime('%b %d %H:%M:%S')}\n")
        info('Starting new Testing instance\n')
        nw_matrix = None
        if args.json_topology:
            error("Direct JSON is not yet supported\n")
            sys.exit()
        if args.topology_file:
            nw_matrix = self.open_file(args.topology_file)

        if not args.json_topology and not args.topology_file:
            nw_matrix = self.open_file(DEFAULT_INPUT_FILE)

        if not nw_matrix:
            error("No topology discovered. Please check input files\n")

        try:
            ping_count = int(args.ping)
        except TypeError as err:
            error('Ping input is not a number, using the default ping '
                  'count of 1\n{err}')

        t_port = None
        if args.thrift_port:
            t_port = args.thrift_port

        if nw_matrix:
            self.parse_config(nw_matrix)
            self.build_network(t_port)
            self.net.start()
            self.cleanup_ips()

            if args.script:
                ATHOS.run_start_script(args.script)

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
            error(f"Error in the input json string\n{err}")
        return data


    def open_file(self, input_file):
        """ Opens the json file that contains the network topology """
        data = None
        try:
            with open(input_file) as json_file:
                data = json.load(json_file)
        except (UnicodeDecodeError, PermissionError, ValueError) as err:
            error(f"Error in the file {input_file}\n{err}\n")
        except FileNotFoundError as err:
            error(f"File not found: {input_file}\n")
            if input_file is DEFAULT_INPUT_FILE:
                error("Please specify a default topology in "
                      "/etc/mxitt/topology.json or specify a topology file "
                      f"using the -i --input option\n{err}\n")
                sys.exit()

        return data

    @staticmethod
    def run_start_script(script):
        """ Runs specified startup script before continuing. Typical use cases
            would be starting controllers or loading switches with rules """
        call(script, shell=True)


    def parse_config(self, nw_matrix):
        """ Parses and validates the config """
        err_msg = "Malformed config detected! "
        try:
            if "hosts_matrix" not in nw_matrix:
                raise ConfigError(f"{err_msg}No 'hosts_matrix' found\n")
            if "switch_matrix" not in nw_matrix:
                raise ConfigError(f"{err_msg}No 'hosts_matrix' found\n")
        except ConfigError as err:
            error(err)
            sys.exit()
        self.check_hosts_config(nw_matrix["hosts_matrix"])
        self.check_switch_config(nw_matrix["switch_matrix"])
        self.hosts_matrix = self.flatten_nw_matrix(nw_matrix)


    def check_hosts_config(self, host_matrix):
        """ Parses and validates the hosts matrix """
        err_msg = ("Malformed config detected in the hosts section!\n" +
                   "Please check the config:\n")
        if not host_matrix:
            error(f"{err_msg}The hosts_matrix doesn't have any content\n")

        for host in host_matrix:
            malformed = False
            if "name" not in host:
                error(f"{err_msg}Entry detected without a name\n")
                malformed = True

            if "interfaces" not in host:
                error(f"{err_msg}Entry detected without any interfaces\n")
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
            error(err + "\n")
            sys.exit()

    def check_ipv4_address(self, err_msg, v4_address):
        """ Checks validity of ipv4 address """
        try:
            if not v4_address:
                raise ConfigError(f"{err_msg} please check that ipv4 sections "
                                  "have addresses assigned\n")
            if "." not in v4_address or "/" not in v4_address:
                raise ConfigError(f"{err_msg} in the ipv4 section\n"
                                  f"IPv4 section: {v4_address}\n")
        except ConfigError as err:
            error(err)
            sys.exit()


    def check_ipv6_address(self, err_msg, v6_address):
        """ Checks validity of ipv6 address """
        try:
            if not v6_address:
                raise ConfigError(f"{err_msg} please check that ipv6 sections" +
                                  "have addresses assigned\n")
            if ":" not in v6_address or "/" not in v6_address:
                raise ConfigError(f"{err_msg} in the ipv6 section\n" +
                                  f"IPv6 section: {v6_address}\n")
        except ConfigError as err:
            error(err)
            sys.exit()


    def check_mac_address(self, err_msg, mac_address):
        """ Checks validity of MAC address """
        try:
            if not mac_address:
                raise ConfigError(f"{err_msg} please check that MAC sections" +
                                  "have addresses assigned\n")
            if ":" not in mac_address:
                raise ConfigError(f"{err_msg} in the MAC section. Currently "
                                  "only addresses seperated with : is "
                                  f"supported.\nMAC section: {mac_address}\n")
        except ConfigError as err:
            error(err)
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
                                  "No mac address was provided\n")
        except ConfigError as err:
            error(err)

        return mac


    def check_vlan_validity(self, err_msg, vlan):
        """ Checks that the assigned vlan is a valid value """
        try:
            vid = int(vlan)
            if vid < 0 or vid > 4095:
                raise ConfigError(f"{err_msg}. Invalid vlan id(vid) detected. "
                                  "A valid vid should be between 1 and 4095.\n"
                                  f"Found vid: {vid}\n")
        except (ConfigError, ValueError) as err:
            error(err)
            sys.exit()

    def packet_loss_threshold_passed(self, v4_loss, v6_loss, src_switch=None,
                                     dst_switch=None, status=""):
        """ Helper to check packet loss and if it is more than the
            maximum allowed """
        link_error_msg = ""
        if src_switch and dst_switch:
            link_error_msg = (f" when the link between {src_switch} and "
                              f"{dst_switch} was set {status}.")
        else:
            link_error_msg = (f" before any links were changed.")

        if v4_loss and v4_loss > self.ploss_threshold \
            and v6_loss and v6_loss > self.ploss_threshold:
            error(f"FAIL: Reachability failed for both IPv4 and IPv6"
                  f"{link_error_msg}")
            error(f"Packet loss threshold: {self.ploss_threshold}\n"
                  f"IPv4 loss: {v4_loss}\tIPv6 loss: {v6_loss}")
            return False
        elif v4_loss and v4_loss > self.ploss_threshold:
            error(f"FAIL: Reachability failed for IPv4{link_error_msg}\n")
            error(f"Packet loss threshold: {self.ploss_threshold}\n"
                  f"IPv4 loss: {v4_loss}")
            return False
        elif v6_loss and v6_loss > self.ploss_threshold:
            error(f"FAIL: Reachability failed for IPv6{link_error_msg}\n")
            error(f"Packet loss threshold: {self.ploss_threshold}\t"
                  f"IPv6 loss: {v6_loss}")
            return False
        else:
            return True


    def check_switch_config(self, sw_matrix):
        """ Parses and validates the switch matrix """
        err_msg = ("Malformed config detected in the switch section!\n" +
                   "Please check the config:\n")
        try:
            if not sw_matrix:
                raise ConfigError(f"{err_msg}Switch matrix is empty\n")
            if "links" not in sw_matrix:
                raise ConfigError(f"{err_msg}No links section found\n")
            for link in sw_matrix["links"]:
                if len(link) != 4:
                    raise ConfigError(f"{err_msg}Invalid link found. The "
                        "expected link format should be:\n"
                        "[switchA,portA,switchB,portB]\nWhere portA is the port"
                        " on switchA connected to switchB, and vice versa "
                        f"for portB\nLink found: {link}\n")
                port_a = int(link[1])
                port_b = int(link[3])

                if port_a < 0 or port_a > 255 or port_b < 0 or port_b > 255:
                    raise ConfigError("Invalid port number detected. Ensure "
                                      "that port numbers are between 0 and 255 "
                                      f"sw1_port: {port_a}\t sw2_port:{port_b}\n")
            if "dp_ids" not in sw_matrix:
                warn(f"{err_msg}No dp_id section found, dp_ids generated in "
                     "Mininet might not match those in controller config\n")
            else:
                for _, dp_id in sw_matrix["dp_ids"].items():
                    if not hex(dp_id):
                        raise ConfigError(f"{err_msg}Please ensure that dp_ids "
                                          "are valid numbers\n")
                self.switch_dps = sw_matrix["dp_ids"]
            if "p4" in sw_matrix:
                self.p4_switches = sw_matrix["p4"]
            if "unmanaged_switches" in sw_matrix:
                self.unmanaged_switches = sw_matrix["unmanaged_switches"]
            self.link_matrix = sw_matrix["links"]

        except ConfigError as err:
            error(err)
            sys.exit()
        except ValueError as err:
            error(f"{err_msg}Please check value of port numbers and vlan ids\n")
            error(err)
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


    class MyTopo(Topo):
        """ Custom topology generator """

        def __init__(self, hosts_matrix=None, switch_matrix=None,
                     switch_dps=None, p4_switches=None,
                     unmanaged_switches=None,
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
                info('Adding p4 switches:')
                i = 0
                for sw in p4_switches:
                    info(f'{sw}')
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
            if unmanaged_switches:
                for sw in unmanaged_switches:
                    self.addSwitch(sw, failMode="standalone")
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
            if "ipv4" in host and "tagged" in host and not host["tagged"]:
                self.addHost(hname, ip=host["ipv4"], mac=host["mac"],
                             intf="eth-0")
            else:
                self.addHost(hname, ip="127.0.0.1/32", mac=host["mac"],
                             intf="eth-0")
            self.addLink(host["switch"], hname, host["swport"])


class ConfigError(Exception):
    """ Exception handler for misconfigured configurations """
    pass
