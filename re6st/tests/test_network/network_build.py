import ipaddress
import logging
import nemu
import time
import weakref
from subprocess import DEVNULL, PIPE
from pathlib import Path

from re6st.tests import DEMO_PATH

fix_file = DEMO_PATH / "fixnemu.py"
# execfile(str(fix_file)) Removed in python3
exec(open(str(fix_file)).read())
IPTABLES = 'iptables-nft'

class ConnectableError(Exception):
    pass

class Node(nemu.Node):
    """simple nemu.Node used for registry and nodes"""
    def __init__(self):
        super(Node, self).__init__()
        self.Popen(('sysctl', '-q',
                    'net.ipv4.icmp_echo_ignore_broadcasts=0')).wait()

    def _add_interface(self, iface):
        self.iface = iface
        iface.__dict__['node'] = weakref.proxy(self)
        return super(Node, self)._add_interface(iface)

    @property
    def ip(self):
        try:
            return str(self._ip)
        except AttributeError:
            # return 1 ipv4 address of the one interface, reverse mode
            for iface in self.get_interfaces()[::-1]:
                for addr in iface.get_addresses():
                    addr = addr['address']
                    if '.' in addr:
                        #TODO different type problem?
                        self._ip = addr
                        return addr


    def connect_switch(self, switch, ip, prefix_len=24):
        self.if_s = if_s = nemu.NodeInterface(self)
        switch.connect(if_s)
        if_s.up = True
        if_s.add_v4_address(ip, prefix_len=prefix_len)
        return if_s

class NetManager:
    """contain all the nemu object created, so they can live more time"""
    def __init__(self):
        self.object = []
        self.registries = {}
    def connectable_test(self):
        """test each node can ping to their registry
        Raise:
            AssertionError
        """
        for reg, nodes in self.registries.items():
            for node in nodes:
                with node.Popen(["ping", "-c", "1", reg.ip], stdout=DEVNULL) as app0:
                    ret = app0.wait()
                if ret:
                    raise ConnectableError(
                        "network construct failed {} to {}".format(node.ip, reg.ip))

        logging.debug("each node can ping to their registry")


def net_route():
    """build a network connect by a route(bridge)

    Returns:
        a network manager contain 3 nodes
    """
    nm = NetManager()

    switch1 = nemu.Switch()
    switch1.up = True

    registry = Node()
    machine1 = Node()
    machine2 = Node()

    registry.connect_switch(switch1, "192.168.1.1")
    machine1.connect_switch(switch1, "192.168.1.2")
    machine2.connect_switch(switch1, "192.168.1.3")

    nm.object.append(switch1)
    nm.registries[registry] = [machine1, machine2]

    nm.connectable_test()
    return nm

def net_demo():

    internet = Node()
    gateway1 = Node()
    gateway2 = Node()

    registry = Node()
    m1 = Node()
    m2 = Node()
    m3 = Node()
    m4 = Node()
    m5 = Node()
    m6 = Node()
    m7 = Node()
    m8 = Node()

    switch1 = nemu.Switch()
    switch2 = nemu.Switch()
    switch3 = nemu.Switch()

    nm = NetManager()
    nm.object = [internet, switch3, switch1, switch2, gateway1, gateway2]
    nm.registries = {registry: [m1, m2, m3, m4, m5, m6, m7, m8]}

    # for node in [g1, m3, m4, m5]:
    #     print "pid: {}".format(node.pid)

    re_if_0, in_if_0 = nemu.P2PInterface.create_pair(registry, internet)
    g1_if_0, in_if_1 = nemu.P2PInterface.create_pair(gateway1, internet)
    g2_if_0, in_if_2 = nemu.P2PInterface.create_pair(gateway2, internet)

    re_if_0.add_v4_address(address="10.0.0.2", prefix_len=24)
    in_if_0.add_v4_address(address='10.0.0.1', prefix_len=24)
    in_if_1.add_v4_address(address='10.1.0.1', prefix_len=24)
    in_if_2.add_v4_address(address='10.2.0.1', prefix_len=24)
    g1_if_0.add_v4_address(address='10.1.0.2', prefix_len=24)
    g2_if_0.add_v4_address(address='10.2.0.2', prefix_len=24)

    for iface in [re_if_0, in_if_0, g1_if_0, in_if_1, g2_if_0, in_if_2]:
        nm.object.append(iface)
        iface.up = True

    ip = ipaddress.ip_address(u"10.1.1.1")
    for i, node in enumerate([gateway1, m1, m2]):
        iface = node.connect_switch(switch1, str(ip + i))
        nm.object.append(iface)
        if i: # except the first
            node.add_route(nexthop=ip)

    gateway1.Popen((IPTABLES, '-t', 'nat', '-A', 'POSTROUTING', '-o', g1_if_0.name, '-j', 'MASQUERADE')).wait()
    gateway1.Popen((IPTABLES, '-t', 'nat', '-N', 'MINIUPNPD')).wait()
    gateway1.Popen((IPTABLES, '-t', 'nat', '-A', 'PREROUTING', '-i', g1_if_0.name, '-j', 'MINIUPNPD')).wait()
    gateway1.Popen((IPTABLES, '-N', 'MINIUPNPD')).wait()


    ip = ipaddress.ip_address(u"10.2.1.1")
    for i, node in enumerate([gateway2, m3, m4, m5]):
        iface = node.connect_switch(switch1, str(ip + i))
        nm.object.append(iface)
        if i: # except the first
            node.add_route(prefix='10.0.0.0', prefix_len=8, nexthop=ip)

    ip = ipaddress.ip_address(u"10.0.1.1")
    for i, node in enumerate([internet, m6, m7, m8]):
        iface = node.connect_switch(switch2, str(ip + i))
        nm.object.append(iface)
        if i: # except the first
            node.add_route(prefix='10.0.0.0', prefix_len=8, nexthop=ip)

    registry.add_route(prefix='10.0.0.0', prefix_len=8, nexthop='10.0.0.1')
    gateway1.add_route(prefix='10.0.0.0', prefix_len=8, nexthop='10.1.0.1')
    gateway2.add_route(prefix='10.0.0.0', prefix_len=8, nexthop='10.2.0.1')
    internet.add_route(prefix='10.2.0.0', prefix_len=16, nexthop='10.2.0.2')

    MINIUPnP_CONF = Path(__file__).parent / 'miniupnpd.conf'
    gateway1.proc = gateway1.Popen(['miniupnpd', '-d', '-f', MINIUPnP_CONF,
                                    '-P', 'miniupnpd.pid', '-a', gateway1.if_s.name,
                                    '-i', g1_if_0.name],
                                   stdout=PIPE, stderr=PIPE)

    switch1.up = switch2.up = switch3.up = True
    nm.connectable_test()
    return nm

def network_direct():
    """one server and one client connect direct"""
    registry = Node()
    m0 = Node()
    nm = NetManager()
    nm.registries = {registry: [m0]}

    re_if_0, m_if_0 = nemu.P2PInterface.create_pair(registry, m0)

    registry._ip = u"10.1.2.1"
    re_if_0.add_v4_address(u"10.1.2.1", prefix_len=24)

    m_if_0.add_v4_address(u"10.1.2.2", prefix_len=24)
    re_if_0.up = m_if_0.up = True

    nm.connectable_test()
    return nm

if __name__ == "__main__":
    nm = net_demo()
    time.sleep(1000000)
