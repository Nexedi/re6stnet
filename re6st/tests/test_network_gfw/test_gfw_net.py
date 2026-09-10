import logging
import os
import time
import unittest

import network_build_gfw
from re6st.tests.test_network import re6st_wrap, test_net


@unittest.skipIf(os.geteuid(), "Using root or creating a user namespace")
class TestGFWNet(unittest.TestCase):
    """network with gfw test case"""

    @classmethod
    def setUpClass(cls):
        """create work dir"""
        logging.basicConfig(level=logging.INFO)
        re6st_wrap.initial()

    @classmethod
    def tearDownClass(cls):
        """watch any process leaked after tests"""
        logging.basicConfig(level=logging.WARNING)

    def test_gfw_ping(self):
        """create a network in a net segment, test the connectivity by ping"""
        nm = network_build_gfw.net_gfw()
        nodes, _ = test_net.deploy_re6st(nm)

        test_net.wait_stable(nodes, 40)
        time.sleep(10)

        self.assertFalse(test_net.wait_stable(nodes, 30), " ping test success")
