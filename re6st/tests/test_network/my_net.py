"""thie moudle use net namespace to create different net node"""

import subprocess
from subprocess import PIPE
import weakref
import logging
import time
import ipaddress

#iptables-legacy seems have permission problem on test-node
IPTABLES = "iptables-nft"

class NetManager(object):
    """contain all the nemu object created, so they can live more time"""
    def __init__(self):
        self.object = []
        self.registrys = {}


class Device(object):
    """class for network device"""
    _id = 0

    @classmethod
    def get_id(cls):
        cls._id += 1
        return cls._id

    def __init__(self, dev_type, name=None):
        """
        type: device type, str
        name: device name, str. if not set, generate one name
        """
        # name if name else .....
        self.type = dev_type
        self.name = name or "{}-{}".format(dev_type, self.get_id())
        self.ips = []
        self._up = False

    @property
    def up(self):
        "bool value control device up or not"
        return self._up

    @up.setter
    def up(self, value):
        value = "up" if value else "down"
        self.net.run(['ip', 'link', 'set', 'up', self.name])

    def add_ip4(self, address, prefix):
        ip = "{}/{}".format(address, prefix)
        self.ips.append(address)
        self.net.run(['ip', 'addr', 'add', ip, 'dev', self.name])


class Netns(object):
    """a network namespace"""

    def __init__(self):
        self.devices = []
        self.app = subprocess.Popen(['unshare', '-n'], stdin=PIPE)
        self.pid = self.app.pid
        self.add_device_lo()

        self.run(['sysctl', '-w', 'net.ipv4.ip_forward=1'], stdout=PIPE)
        self.run(['sysctl', '-w', 'net.ipv6.conf.default.forwarding=1'],
                 stdout=PIPE)

    def Popen(self, cmd, **kw):
        """ wrapper for subprocess.Popen"""
        return subprocess.Popen(['nsenter', '-t', str(self.pid), '-n'] + cmd, **kw)

    def run(self, cmd, **kw):
        """ wrapper for subprocess.checkout"""
        subprocess.check_call(['nsenter', '-t', str(self.pid), '-n'] + cmd, **kw)

    def add_device(self, dev):
        self.devices.append(dev)
        dev.net = weakref.proxy(self)

    def add_device_lo(self):
        lo = Device("lo", name="lo")
        self.add_device(lo)
        lo.up = True

    def add_device_bridge(self):
        """ create a bridge in the netns"""
        br = Device("bridge")
        self.add_device(br)
        self.bridge = br
        self.run(['ip', 'link', 'add', br.name, 'type', 'bridge'])
        br.up = True

    def add_route(self, net, *args):
        self.run(['ip', 'route', 'add', net] + list(args))

    def connect_direct(node1, node2):
        """create veths between 2 netns
        no difference if node1 and node2 changed
        Args:
            node1(self): Netns
            node2: Netns
        """
        dev1 = Device("veth")
        dev2 = Device("veth")
        node1.add_device(dev1)
        node2.add_device(dev2)
        subprocess.check_call(['ip', 'link', 'add', dev1.name, 'netns', str(node1.pid), 'type', 'veth', 'peer', dev2.name, 'netns', str(node2.pid)])
        dev1.up = dev2.up = True
        return dev1, dev2

    def connect_router(self, router):
        """ connect a netns to a router

        create veths between 2 netns, and set one veth to the bridge
        in router
        Args:
            router: Netns

        Retruns:
            device(self), device(router)
        """
        if not hasattr(router, "bridge"):
            raise Exception("router should have a bridge")

        dev1, dev2 = self.connect_direct(router)
        self.add_device(dev1)
        router.add_device(dev2)

        router.run(['ip', 'link', 'set', dev2.name, 'master', router.bridge.name])
        return dev1, dev2

    def __del__(self):
        self.app.terminate()
        self.app.wait()

        if hasattr(self, "proc"):
            self.proc.terminate()
            self.proc.wait()


class Host(Netns):
    """node used to run a application, not for connecting

    use the first create veth as out, and it's ip for re6st config
    """

    @property
    def ip(self):
        return self.out.ips[0]

    @property
    def out(self):
        return self.devices[1]

def connectible_test(nm):
    """test each node can ping to their registry

    Args:
        nm: NetManger

    Raise:
        AssertionError
    """
    for reg in nm.registrys:
        for node in nm.registrys[reg]:
            app0 = node.Popen(["ping", "-c", "1", reg.ip], stdout=PIPE)
            ret = app0.wait()
            assert ret == 0, "network construct failed {} to {}".format(node.ip, reg.ip)

    logging.debug("each node can ping to their registry")

def net_simple():
    """build a simplest network

    registry .1 ------ .2 node
                10.1.1

    Returns:
        a network manager contain 2 nodes
    """
    nm = NetManager()
    node1 = Host()
    node2 = Host()
    dev1, dev2 = node1.connect_direct(node2)
    dev1.add_ip4("10.1.1.1", prefix=24)
    dev2.add_ip4("10.1.1.2", prefix=24)

    nm.registrys[node1] = [node2]
    connectible_test(nm)

    return nm

def net_route():
    """build a network connect by a route(bridge)

    Returns:
        a network manager contain 3 nodes
    """

    nm = NetManager()

    router = Netns()
    router.add_device_bridge()

    registry = Host()
    node1 = Host()
    node2 = Host()

    veth_r, _ = registry.connect_router(router)
    veth_n1, _ = node1.connect_router(router)
    veth_n2, _ = node2.connect_router(router)

    veth_r.add_ip4("192.168.1.1", 24)
    veth_n1.add_ip4("192.168.1.2", 24)
    veth_n2.add_ip4("192.168.1.3", 24)

    nm.object.append(router)
    nm.registrys[registry] = [node1, node2]

    connectible_test(nm)
    return nm

def net_demo():
    """build a network like demo
    Underlying network:

        registry .2------
                        |
                    10.0.0|
                    .1 |
        ---------------Internet----------------
        |.1                |.1                |.1
        |10.1.0            |10.2.0            |
        |.2                |.2                |
    gateway1           gateway2           s3:10.0.1
        |.1                |.1            |.2 |.3 |.4
    s1:10.1.1        --s2:10.2.1--        m6  m7  m8
    |.2     |.3      |.2 |.3 |.4
    m1      m2       m3  m4  m5

    Return:
        a network manager contain 9 nodes
    """
    nm = NetManager()

    internet = Netns()
    gateway1 = Netns()
    router1 = Netns()
    gateway2 = Netns()
    router2 = Netns()
    router3 = Netns()

    registry = Host()
    node1 = Host()
    node2 = Host()
    node3 = Host()
    node4 = Host()
    node5 = Host()
    node6 = Host()
    node7 = Host()
    node8 = Host()

    router1.add_device_bridge()
    router2.add_device_bridge()
    router3.add_device_bridge()

    veth_re, veth_it1 = registry.connect_direct(internet)
    veth_g1_1, veth_it2 = gateway1.connect_direct(internet)
    veth_g2_1, veth_it3 = gateway2.connect_direct(internet)


    veth_it1.add_ip4("10.0.0.1", 24)
    veth_re.add_ip4("10.0.0.2", 24)
    registry.add_route("10.0.0.0/8", 'via', "10.0.0.1")

    veth_it2.add_ip4("10.1.0.1", 24)
    veth_g1_1.add_ip4("10.1.0.2", 24)
    gateway1.add_route("10.0.0.0/8", 'via', "10.1.0.1")

    # sign ip for node
    ip = ipaddress.ip_address(u"10.1.1.1")
    for node in [gateway1, node1, node2]:
        dev, _ = node.connect_router(router1)
        dev.add_ip4(str(ip), 24)
        ip += 1
    for node in [node1, node2]:
        node.add_route("10.0.0.0/8", 'via', "10.1.1.1")

    gateway1.run([IPTABLES, '-t', 'nat', '-A', 'POSTROUTING', '-o', veth_g1_1.name, '-j', 'MASQUERADE'])
    gateway1.run([IPTABLES, '-t', 'nat', '-N', 'MINIUPNPD'])
    gateway1.run([IPTABLES, '-t', 'nat', '-A', 'PREROUTING', '-i', veth_g1_1.name, '-j', 'MINIUPNPD'])
    gateway1.run([IPTABLES, '-N', 'MINIUPNPD'])

    veth_it3.add_ip4("10.2.0.1", 24)
    veth_g2_1.add_ip4("10.2.0.2", 24)
    gateway2.add_route("10.0.0.0/8", 'via', "10.2.0.1")

    ip = ipaddress.ip_address(u"10.2.1.1")
    for node in [gateway2, node3, node4, node5]:
        dev, _ = node.connect_router(router2)
        dev.add_ip4(str(ip), 24)
        ip += 1
    for node in [node3, node4, node5]:
        node.add_route("10.0.0.0/8", 'via', "10.2.1.1")

    ip = ipaddress.ip_address(u"10.0.1.1")
    for node in [internet, node6, node7, node8]:
        dev, _ = node.connect_router(router3)
        dev.add_ip4(str(ip), 24)
        ip += 1
    for node in [node6, node7, node8]:
        node.add_route("10.0.0.0/8", 'via', "10.0.1.1")

    # internet.add_route("10.1.0.0/16", 'via', "10.1.0.2")
    internet.add_route("10.2.0.0/16", 'via', "10.2.0.2")


    gateway1.proc = gateway1.Popen(['miniupnpd', '-d', '-f', 'miniupnpd.conf', '-P', 'miniupnpd.pid',
                                    '-a', gateway1.devices[-1].name, '-i', gateway1.devices[-1].name],
                                   stdout=PIPE, stderr=PIPE)

    nm.object += [internet, gateway1, gateway2, router1, router2, router3]
    nm.registrys[registry] = [node1, node2, node3, node4, node5, node6, node7, node8]

    connectible_test(nm)

    return nm

if __name__ == "__main__":
    net_demo()
    print("good bye!")
