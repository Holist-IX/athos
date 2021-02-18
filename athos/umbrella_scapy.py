""" Custom switch written to work with umbrella architecture """

from logging import exception
import threading
import logging
import pdb
from mininet.node import OVSSwitch
from netaddr.eui import EUI
from scapy.all import conf, sniff


class UmbrellaScapy(OVSSwitch):
    """ Custom switch that acts as an Open vSwitch, but has scapy compatability
        to do the rewrite that is needed for Umbrella architecture. This is to
        act as a lightweight p4 substitute to be used within mininet """


    def __init__(self, name, failMode='secure', datapath='kernel',
                 inband=False, protocols=None, reconnectms=1000,
                 stp=False, batch=False, **params):
        super(UmbrellaScapy, self).__init__(name, **params)
        self.failMode = failMode
        self.datapath = datapath
        self.inband = inband
        self.protocols = protocols
        self.reconnectms = reconnectms
        self.stp = stp
        self.batch = batch
        self._uuids = []
        self.commands = []
        self.threads = []
        self.listening_sockets = {}


    def start(self, controllers):
        """ Starts the switch """
        for intf in self.intfs.values():
            if intf.name == "lo":
                continue
            socket = conf.L2socket(iface=intf.name)
            self.listening_sockets[intf] = socket
            thread = threading.Thread(target=self.launch, kwargs={"intf": intf.name})
            thread.daemon = True
            thread.start()
            self.threads.append(thread)

        super(UmbrellaScapy, self).start(controllers)


    def launch(self, intf):
        """ Launches the scapy module """
        # try:
        sniff(prn=self.forwarding,
                filter=f"inbound",
                iface=intf)
        # except Exception:
        #     logging.error(exception)
        #     logging.error(f"Interface {intf} is down")


    def stop(self):
        """ Stops all the threads """
        for thread in self.threads:
            thread.join(1)
        for socket in self.listening_sockets.values():
            socket.close()
        super(UmbrellaScapy, self).stop()


    def forwarding(self, pkt):
        """ Forwards the packet based on the umbrella principle """
        
        mac = EUI(pkt.dst)
        dst = pkt.dst
        p = dst.split(':')[0]
        port_num = int(p, 16)
        if int(port_num) in self.intfs:
            mac_shift = int(mac) & 0x00FFFFFFFFFF
            mac_shifted = mac_shift << 8
            new_mac = EUI(addr=mac_shifted)
            pkt.dst = str(new_mac).replace('-', ':')
            try:
                self.listening_sockets.get(
                    self.intfs.get(int(port_num)), None).send(pkt)
            except AttributeError:
                logging.warning(
                    f"Tried to send a packet to unknown port: {port_num}")
        else:
            logging.warning(
                f"Port {port_num} designated is not set on switch")
