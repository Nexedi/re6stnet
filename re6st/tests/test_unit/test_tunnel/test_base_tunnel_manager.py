#!/usr/bin/python2
import os
import sys
import unittest
import time
from mock import patch, Mock


from re6st import tunnel
from re6st import x509
from re6st import cache

from re6st.tests import tools

class testBaseTunnelManager(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ca_key, ca = tools.create_ca_file("ca.key", "ca.cert")
        tools.create_cert_file("node.key", "node.cert", ca, ca_key, "00000001", 1)
        cls.cert = x509.Cert("ca.cert", "node.key", "node.cert")
        cls.control_socket = "babeld.sock"


    def setUp(self):
        patcher = patch("re6st.cache.Cache")
        pacher_sock = patch("socket.socket")
        self.addCleanup(patcher.stop)
        self.addCleanup(pacher_sock.stop)
        self.cache = patcher.start()()
        self.sock = pacher_sock.start()
        self.cache.same_country = False

        address = [(2, [('10.0.0.2', '1194', 'udp'), ('10.0.0.2', '1194', 'tcp')])]
        self.tunnel = tunnel.BaseTunnelManager(self.control_socket,
            self.cache, self.cert, None, address)

    def tearDown(self):
        self.tunnel.close()
        del self.tunnel

    #TODO selectTimeout in contain callback, removing, update

    @patch("re6st.tunnel.BaseTunnelManager.selectTimeout")
    def test_invalidatePeers(self, selectTimeout):
        """normal case, stop_date: p2 < now < p1 < p3
        expect:
            _peers ->  [p1, p3]
            next = p1.stoptime
        """
        p1 = x509.Peer("00")
        p2 = x509.Peer("01")
        p3 = x509.Peer("10")
        p1.stop_date = time.time() + 1000
        p2.stop_date = 1
        p3.stop_date = p1.stop_date + 500
        self.tunnel._peers = [p1, p2, p3]

        self.tunnel.invalidatePeers()

        self.assertEqual(self.tunnel._peers, [p1, p3])
        selectTimeout.assert_called_once_with(p1.stop_date, self.tunnel.invalidatePeers)


    # Because _makeTunnel is defined in sub class of BaseTunnelManager, so i comment
    # the follow test
    # @patch("re6st.tunnel.BaseTunnelManager._makeTunnel", create=True)
    # def test_processPacket_address_with_msg_peer(self, makeTunnel):
    #     """code is 1, peer and msg not none """
    #     c = chr(1)
    #     msg = "address"
    #     peer = x509.Peer("000001")
    #     self.tunnel._connecting = {peer}

    #     self.tunnel._processPacket(c + msg, peer)

    #     self.cache.addPeer.assert_called_once_with(peer, msg)
    #     self.assertFalse(self.tunnel._connecting)
    #     makeTunnel.assert_called_once_with(peer, msg)


    def test_processPacket_address(self):
        """code is 1, for address. And peer or msg are none"""
        c = chr(1)
        self.tunnel._address = {1: "1,1", 2: "2,2"}

        res = self.tunnel._processPacket(c)

        self.assertEqual(res, "1,1;2,2")


    def test_processPacket_address_with_peer(self):
        """code is 1, peer is not none, msg is none
        in my opion, this function return address in form address,port,portocl
        and each address join by ;
        it will truncate address which has more than 3 element
        """
        c = chr(1)
        peer = x509.Peer("000001")
        peer.protocol = 1
        self.tunnel._peers.append(peer)
        self.tunnel._address = {1: "1,1,1;0,0,0", 2: "2,2,2,2"}

        res = self.tunnel._processPacket(c, peer)

        self.assertEqual(res, "1,1,1;0,0,0;2,2,2")

    @patch("re6st.x509.Cert.verifyVersion", Mock(return_value=True))
    @patch("re6st.tunnel.BaseTunnelManager.selectTimeout")
    def test_processPacket_version(self, selectTimeout):
        """code is 0, for network version, peer is not none
        2 case, one modify the version, one not
        """
        c = chr(0)
        peer = x509.Peer("000001")
        version1 = "00003"
        version2 = "00007"
        self.tunnel._version = version3 = "00005"
        self.tunnel._peers.append(peer)

        res = self.tunnel._processPacket(c + version1, peer)
        self.tunnel._processPacket(c + version2, peer)

        self.assertEqual(res, version3)
        self.assertEqual(self.tunnel._version, version2)
        self.assertEqual(peer.version, version2)
        self.assertEqual(selectTimeout.call_args[0][1], self.tunnel.newVersion)




if __name__ == "__main__":
    unittest.main()


