"""contain ping-test for re6set net"""
import os
import unittest
import time
import psutil
import logging
import sqlite3
import random
from binascii import b2a_hex
from pathlib2 import Path
import re6st_wrap
import  network_build

PING_PATH = str(Path(__file__).parent.resolve() / "ping.py")
BABEL_HMAC = 'babel_hmac0', 'babel_hmac1', 'babel_hmac2'

def deploy_re6st(nm, recreate=False):
    net = nm.registrys
    nodes = []
    registrys = []
    re6st_wrap.Re6stRegistry.registry_seq = 0
    re6st_wrap.Re6stNode.node_seq = 0
    for registry in net:
        reg = re6st_wrap.Re6stRegistry(registry, "2001:db8:42::", len(net[registry]),
                                       recreate=recreate)
        reg_node = re6st_wrap.Re6stNode(registry, reg, name=reg.name)
        registrys.append(reg)
        reg_node.run("--gateway", "--disable-proto", "none", "--ip", registry.ip)
        nodes.append(reg_node)
        for m in net[registry]:
            node = re6st_wrap.Re6stNode(m, reg)
            node.run("-i" + m.iface.name)
            nodes.append(node)
    return nodes, registrys

def wait_stable(nodes, timeout=240):
    """try use ping6 from each node to the other until ping success to all the
    other nodes
    Args:
        timeout: int, the time for wait

    return:
        True if success
    """
    logging.info("wait all node stable, timeout: %s", timeout)
    now = time.time()
    ips = {node.ip6: node.name for node in nodes}
    # start the ping processs
    for node in nodes:
        sub_ips = set(ips) - {node.ip6}
        node.ping_proc = node.node.Popen(
            ["python", PING_PATH, '--retry', '-a'] + list(sub_ips))

    # check all the node network can ping each other, in order reverse
    unfinished = list(nodes)
    while unfinished:
        for i in range(len(unfinished)-1, -1, -1):
            node = unfinished[i]
            if node.ping_proc.poll() is not None:
                logging.debug("%s 's network is stable", node.name)
                unfinished.pop(i)
        time.sleep(0.5)

        if time.time() - now > timeout:
            for node in unfinished:
                node.ping_proc.destroy()
            logging.warn("%s  can't ping to all the nodes", unfinished)
            return False
    logging.info("wait time cost: %s", time.time() - now)
    return True

@unittest.skipIf(os.geteuid() != 0, "require root or create user namespace plz")
class TestNet(unittest.TestCase):
    """ network test case"""

    @classmethod
    def setUpClass(cls):
        """create work dir"""
        logging.basicConfig(level=logging.INFO)
        re6st_wrap.initial()

    @classmethod
    def tearDownClass(cls):
        """watch any process leaked after tests"""
        logging.basicConfig(level=logging.WARNING)
        for p in psutil.Process().children():
            logging.debug("unterminate ps, name: %s, pid: %s, status: %s, cmd: %s",
                          p.name(), p.pid, p.status(), p.cmdline())
            p.terminate()
            # try:
            #     p.kill()
            # except:
            #     pass

    def test_ping_router(self):
        """create a network in a net segment, test the connectivity by ping
        """
        nm = network_build.net_route()
        nodes, _ = deploy_re6st(nm)

        wait_stable(nodes, 40)
        time.sleep(10)

        self.assertTrue(wait_stable(nodes, 30), " ping test failed")

    def test_ping_demo(self):
        """create a network demo, test the connectivity by ping
        wait at most 50 seconds, and test each node ping to other by ipv6 addr
        """
        nm = network_build.net_demo()
        nodes, _ = deploy_re6st(nm)
        # wait 60, if the re6stnet stable quit wait
        wait_stable(nodes, 100)
        time.sleep(20)

        self.assertTrue(wait_stable(nodes, 100), "ping test failed")

    def test_reboot_one_machine(self):
        """create a network demo, wait the net stable, reboot on machine,
        then test if network recover, this test seems always failed
        """
        nm = network_build.net_demo()
        nodes, _ = deploy_re6st(nm)

        wait_stable(nodes, 100)

        # stop on machine randomly
        index = int(random.random() * 7) + 1
        machine = nodes[index]
        machine.stop()
        time.sleep(5)
        machine.run("-i" + machine.node.iface.name)
        logging.info("restart %s", machine.name)

        self.assertTrue(wait_stable(nodes, 400), "network can't recover")

    def test_reboot_one_machine_router(self):
        """create a network router, wait the net stable, reboot on machine,
        then test if network recover,
        """
        nm = network_build.net_route()
        nodes, _ = deploy_re6st(nm)

        wait_stable(nodes, 40)

        # stop on machine randomly
        index = int(random.random() * 2) + 1
        machine = nodes[index]
        machine.stop()
        time.sleep(5)
        machine.run("-i" + machine.node.iface.name)
        logging.info("restart %s", machine.name)

        self.assertTrue(wait_stable(nodes, 100), "network can't recover")



if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, filename='test.log', filemode='w',
                        format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%I:%M:%S')
    unittest.main(verbosity=3)
