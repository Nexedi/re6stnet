
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
import zlib

from re6st import registry, x509
from re6st.tests.test_network import re6st_wrap
from re6st.tests import tools
from re6st.tests import DEMO_PATH

DH_FILE = DEMO_PATH / "dh2048.pem"

class DummyNode:
    """fake node to reuse Re6stRegistry

    error: node.Popen has destory method which not in subprocess.Popen
    """
    def __init__(self):
        self.ip = "localhost"
        self.Popen = subprocess.Popen
        self.pid = os.getpid()

class TestRegistryClientInteract(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        re6st_wrap.initial()

        # if running in net ns, set lo up
        subprocess.check_call(("ip", "link", "set", "lo", "up"))

    def setUp(self):
        self.port = 18080
        self.url = "http://localhost:{}/".format(self.port)
        # not important, used in network_config check
        self.max_clients = 10

    def tearDown(self):
        self.server.proc.terminate()

    def test_1_main(self):
        """ a client interact a server, no re6stnet node test basic function"""
        self.server = re6st_wrap.Re6stRegistry(
                DummyNode(),
                "2001:db8:42::",
                self.max_clients, port=self.port,
                recreate=True)

        client = registry.RegistryClient(self.url)
        email = "m1@miku.com"

        # simulate the process in conf
        # request a token
        client.requestToken(email)
        # read token from db
        db = sqlite3.connect(str(self.server.db), isolation_level=None)
        token = None
        for _ in range(100):
            time.sleep(.1)
            token = db.execute("SELECT token FROM token WHERE email=?",
                               (email,)).fetchone()
            if token:
                break
        else:
            self.fail("Request token failed, no token in database")
        # token: tuple[unicode,]
        token = str(token[0])
        self.assertEqual(client.isToken(token), b"1")

        # request ca
        ca = client.getCa()

        # request a cert and get cn
        key, csr = tools.generate_csr()
        cert = client.requestCertificate(token, csr)
        self.assertEqual(client.isToken(token), b'', "token should be deleted")

        # creat x509.cert object
        def write_to_temp(text):
            """text: bytes"""
            file = tempfile.NamedTemporaryFile()
            file.write(text)
            file.flush()
            return file

        ca, key, cert = map(write_to_temp, (ca, key, cert))
        client.cert = x509.Cert(ca.name, key.name, cert.name)
        ca.close()
        cert.close()
        # cert.decrypt use key file, close after entire test
        self.addCleanup(key.close)

        # verfiy cn and prefix
        prefix = client.cert.prefix
        cn = client.getNodePrefix(email).decode()
        self.assertEqual(tools.prefix2cn(prefix), cn)

        # simulate the process in cache
        # just prove works
        net_config = client.getNetworkConfig(prefix)
        net_config = json.loads(zlib.decompress(net_config))
        self.assertEqual(net_config[u'max_clients'], self.max_clients)

        # no re6stnet, empty result
        bootpeer = client.getBootstrapPeer(prefix)
        self.assertEqual(bootpeer, b"")

        # server should not die
        self.assertIsNone(self.server.proc.poll())

    #TODO with a registry and some node, test babel_dump related function

if __name__ == "__main__":
    unittest.main()
