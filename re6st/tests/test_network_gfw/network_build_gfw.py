#!/bin/python2
import atexit
import ipaddress
from subprocess import PIPE

import nemu
from pathlib2 import Path

from re6st.tests.test_network.network_build import Node, NetManager

GFW = str(Path(__file__).parent.resolve() / "gfw.py")


def net_gfw():
    """Underlying network
        registry .2-----
                       |
                 10.0.0|
                    .1 |
        ---------------Internet
        |.1               |.1
        |10.1.0           |
        |.2               |
    gateway1(GFW)         s3:10.0.1
        |.1           |.2 |.3 |.4
    s1:10.1.1         m3  m4  m5
    |.2     |.3
    m1      m2
    """
    internet = Node()
    gateway1 = Node()
    registry = Node()
    m1 = Node()
    m2 = Node()
    m3 = Node()
    m4 = Node()
    m5 = Node()

    switch1 = nemu.Switch()
    switch2 = nemu.Switch()

    nm = NetManager()
    nm.object = [internet, switch1, switch2, gateway1]
    nm.registries = {registry: [m1, m2, m3, m4, m5]}

    re_if_0, in_if_0 = nemu.P2PInterface.create_pair(registry, internet)
    g1_if_0, in_if_1 = nemu.P2PInterface.create_pair(gateway1, internet)

    re_if_0.add_v4_address(address="10.0.0.2", prefix_len=24)
    in_if_0.add_v4_address(address="10.0.0.1", prefix_len=24)
    g1_if_0.add_v4_address(address="10.1.0.2", prefix_len=24)
    in_if_1.add_v4_address(address="10.1.0.1", prefix_len=24)

    for iface in (re_if_0, in_if_0, g1_if_0, in_if_1):
        nm.object.append(iface)
        iface.up = True

    ip = ipaddress.ip_address(u"10.1.1.1")
    for i, node in enumerate([gateway1, m1, m2]):
        iface = node.connect_switch(switch1, str(ip + i))
        nm.object.append(iface)
        if i:  # except the first
            node.add_route(prefix="10.0.0.0", prefix_len=8, nexthop=ip)

    ip = ipaddress.ip_address(u"10.0.1.1")
    for i, node in enumerate([internet, m3, m4, m5]):
        iface = node.connect_switch(switch2, str(ip + i))
        nm.object.append(iface)
        if i:  # except the first
            node.add_route(prefix="10.0.0.0", prefix_len=8, nexthop=ip)

    registry.add_route(prefix="10.0.0.0", prefix_len=8, nexthop="10.0.0.1")
    gateway1.add_route(prefix="10.0.0.0", prefix_len=8, nexthop="10.1.0.1")
    internet.add_route(prefix="10.1.0.0", prefix_len=16, nexthop="10.1.0.2")

    switch1.up = switch2.up = True
    nm.connectable_test()
    gateway1.gfw = gateway1.Popen(["python3", GFW], stdout=PIPE)
    atexit.register(gateway1.gfw.destroy)

    return nm
