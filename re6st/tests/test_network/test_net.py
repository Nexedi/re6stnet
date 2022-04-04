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
import my_net

PING_PATH = str(Path(__file__).parent.resolve() / "ping.py")
BABEL_HMAC = 'babel_hmac0', 'babel_hmac1', 'babel_hmac2'

def deploy_re6st(nm, recreate=False):
    net = nm.registrys
    nodes = []
    registrys = []
    re6st_wrap.Re6stRegistry.registry_seq = 0
    re6st_wrap.Re6stNode.node_seq = 0
    for registry in net:
        reg = re6st_wrap.Re6stRegistry(registry, "2001:db8:42::", recreate=recreate)
        reg_node = re6st_wrap.Re6stNode(registry, reg, name=reg.name)
        registrys.append(reg)
        reg_node.run("--gateway", "--disable-proto", "none", "--ip", registry.ip)
        nodes.append(reg_node)
        for m in net[registry]:
            node = re6st_wrap.Re6stNode(m, reg)
            node.run("-i" + m.out.name)
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
                node.ping_proc.terminate()
            logging.warn("%s  can't ping to all the nodes", unfinished)
            return False
    logging.info("wait time cost: %s", time.time() - now)
    return True

def get_config(db, name):
    r = db.execute("SELECT value FROM config WHERE name=?", (name,)).fetchone()
    if r:
        return b2a_hex(*r)

def check_HMAC(db, machines):
    """method copy from demo"""
    hmac = [get_config(db, k) for k in BABEL_HMAC]
    rc = True
    for x in psutil.Process().children(True):
        if x.name() == 'babeld':
            sign = accept = None
            args = x.cmdline()
            for x in args:
                if x.endswith('/babeld.log'):
                    if x[:-11].split('/')[-1] not in machines:
                        break
                elif x.startswith('key '):
                    x = x.split()
                    if 'sign' in x:
                        sign = x[-1]
                    elif 'accept' in x:
                        accept = x[-1]
            else:
                i = 0 if hmac[0] else 1
                if hmac[i] != sign or hmac[i+1] != accept:
                    logging.warn('HMAC config wrong for in %s', args)
                    logging.warn("HMAC sign: %s, accept: %s", sign, accept)
                    rc = False
    if rc:
        logging.info('All nodes use Babel with the correct HMAC configuration')
    else:
        logging.warn('Expected config: %s', dict(zip(BABEL_HMAC, hmac)))
    return rc


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
        for p in psutil.Process().children():
            logging.debug("unterminate ps, name: %s, pid: %s, status: %s, cmd: %s",
                          p.name(), p.pid, p.status(), p.cmdline())
            p.terminate()
        logging.basicConfig(level=logging.WARNING)
            # try:
            #     p.kill()
            # except:
            #     pass

    def test_ping_router(self):
        """create a network in a net segment, test the connectivity by ping
        """
        nm = my_net.net_route()
        nodes, _ = deploy_re6st(nm)

        wait_stable(nodes, 40)
        time.sleep(10)

        self.assertTrue(wait_stable(nodes, 30), " ping test failed")

    def test_ping_demo(self):
        """create a network demo, test the connectivity by ping
        wait at most 50 seconds, and test each node ping to other by ipv6 addr
        """
        nm = my_net.net_demo()
        nodes, _ = deploy_re6st(nm)
        # wait 60, if the re6stnet stable quit wait
        wait_stable(nodes, 50)
        time.sleep(20)

        self.assertTrue(wait_stable(nodes, 30), "ping test failed")

    def test_reboot_one_machine(self):
        """create a network demo, wait the net stable, reboot on machine,
        then test if network recover, this test seems always failed
        """
        nm = my_net.net_demo()
        nodes, _ = deploy_re6st(nm)

        wait_stable(nodes, 100)
        # stop on machine randomly
        index = int(random.random() * 7) + 1
        machine = nodes[index]

        machine.proc.terminate()
        machine.proc.wait()
        time.sleep(5)
        machine.run("-i" + machine.node.out.name)

        self.assertTrue(wait_stable(nodes, 100), "network can't recover")

    @unittest.skip("re6st dont use hmac now")
    def test_hmac(self):
        """create a network demo, and run hmac test, this test check hmac 3
        times the third part always failed, unless deploy_re6st in no recreate
        mode
        """
        nm = my_net.net_demo()
        nodes, registrys = deploy_re6st(nm, False)

        updateHMAC = ['python', '-c', "import urllib, sys; sys.exit("
                      "204 != urllib.urlopen('http://127.0.0.1/updateHMAC').code)"]

        registry = registrys[0]
        machine1 = nodes[5]
        reg1_db = sqlite3.connect(str(registry.db), isolation_level=None,
                                  check_same_thread=False)

        # reg1_db.text_factory = str
        m_net1 = [node.name for node in nodes]

        # wait net stable, wait at most 100 seconds
        wait_stable(nodes, 100)

        logging.info('Check that the initial HMAC config is deployed on network 1')
        self.assertTrue(check_HMAC(reg1_db, m_net1), "first hmac check failed")

        logging.info('Test that a HMAC update works with nodes that are up')
        registry.node.run(updateHMAC)
        time.sleep(60)
        # Checking HMAC on machines connected to registry 1...
        self.assertTrue(check_HMAC(reg1_db, m_net1),
                        "second hmac check failed: HMAC update don't work")

        # # check if one machine restarted
        logging.info('Test that machines can update upon reboot '
                     'when they were off during a HMAC update.')
        machine1.stop()
        time.sleep(5)
        registry.node.run(updateHMAC)
        time.sleep(60)
        machine1.run("-i" + machine1.node.out.name)
        wait_stable(nodes, 100)
        self.assertTrue(check_HMAC(reg1_db, m_net1),
                        "third hmac check failed: machine restart failed")
        logging.info('Testing of HMAC done!')
        reg1_db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, filename='test.log', filemode='w',
                        format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%I:%M:%S')
    unittest.main(verbosity=3)
