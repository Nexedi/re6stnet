"""contain ping-test for re6set net"""
import os
import sys
import unittest
import time
import psutil
import logging
import random
from pathlib import Path

from . import network_build, re6st_wrap

PING_PATH = str(Path(__file__).parent.resolve() / "ping.py")

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
            [sys.executable, PING_PATH, '--retry', '-a'] + list(sub_ips), env=os.environ)

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
            logging.warning("%s  can't ping to all the nodes", unfinished)
            return False
    logging.info("wait time cost: %s", time.time() - now)
    return True

@unittest.skipIf(os.geteuid(), "Using root or creating a user namespace")
class TestNet(unittest.TestCase):
    """ network test case"""

    @classmethod
    def setUpClass(cls):
        """create work dir"""
        logging.basicConfig(level=logging.INFO)
        re6st_wrap.initial()

    def deploy_re6st(self, nm, recreate=False):
        net = nm.registries
        nodes = []
        registries = []
        re6st_wrap.Re6stRegistry.registry_seq = 0
        re6st_wrap.Re6stNode.node_seq = 0
        for registry in net:
            reg = re6st_wrap.Re6stRegistry(registry, "2001:db8:42::", len(net[registry]),
                                           recreate=recreate)
            reg_node = re6st_wrap.Re6stNode(registry, reg, name=reg.name)
            registries.append(reg)
            reg_node.run("--gateway", "--disable-proto", "none", "--ip", registry.ip)
            nodes.append(reg_node)
            for m in net[registry]:
                node = re6st_wrap.Re6stNode(m, reg)
                node.run("-i" + m.iface.name)
                nodes.append(node)

        def clean_re6st():
            for node in nodes:
                node.node.destroy()
                node.stop()

            for reg in registries:
                with reg as r:
                    r.terminate()

        self.addCleanup(clean_re6st)

        return nodes, registries

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
        nodes, registries = self.deploy_re6st(nm)

        wait_stable(nodes, 40)
        time.sleep(10)

        self.assertTrue(wait_stable(nodes, 30), " ping test failed")

    @unittest.skip("usually failed due to UPnP problem")
    def test_reboot_one_machine(self):
        """create a network demo, wait the net stable, reboot on machine,
        then test if network recover, this test seems always failed
        """
        nm = network_build.net_demo()
        nodes, registries = self.deploy_re6st(nm)

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
        nodes, registries = self.deploy_re6st(nm)

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
