import sys
import os
import unittest
import hmac
import http.client
import base64
import hashlib
from mock import Mock, patch

from re6st import registry

class TestRegistryClient(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        server_url = "http://10.0.0.2/"
        cls.client = registry.RegistryClient(server_url)
        cls.client._conn = Mock()

    def test_init(self):
        url1 = "https://localhost/example/"
        url2 = "http://10.0.0.2/"

        client1 = registry.RegistryClient(url1)
        client2 = registry.RegistryClient(url2)

        self.assertEqual(client1._path, "/example")
        self.assertEqual(client1._conn.host, "localhost")
        self.assertIsInstance(client1._conn, http.client.HTTPSConnection)
        self.assertIsInstance(client2._conn, http.client.HTTPConnection)

    def test_rpc_hello(self):
        prefix = "0000000011111111"
        protocol = "7"
        body = "a_hmac_key"
        query = "/hello?client_prefix=0000000011111111&protocol=7"
        response = fakeResponse(body, http.client.OK)
        self.client._conn.getresponse.return_value = response

        res = self.client.hello(prefix, protocol)

        self.assertEqual(res, body)
        conn = self.client._conn
        conn.putrequest.assert_called_once_with('GET', query, skip_accept_encoding=1)
        conn.close.assert_not_called()
        conn.endheaders.assert_called_once()

    def test_rpc_with_cn(self):
        query = "/getNetworkConfig?cn=0000000011111111"
        cn =  "0000000011111111"
        # hmac part
        self.client._hmac = None
        self.client.hello = Mock(return_value = "aaabbb")
        self.client.cert = Mock()
        key = b"this_is_a_key"
        self.client.cert.decrypt.return_value = key
        h = hmac.HMAC(key, query.encode(), hashlib.sha1).digest()
        key = hashlib.sha1(key).digest()
        # response part
        body = b'this is a body'
        response = fakeResponse(body, http.client.NO_CONTENT)
        response.msg = dict(Re6stHMAC=base64.b64encode(hmac.HMAC(key, body, hashlib.sha1).digest()))
        self.client._conn.getresponse.return_value = response

        res = self.client.getNetworkConfig(cn)

        self.client.cert.verify.assert_called_once_with("bbb", "aaa")
        self.assertEqual(self.client._hmac, hashlib.sha1(key).digest())
        conn = self.client._conn
        conn.putheader.assert_called_with("Re6stHMAC", base64.b64encode(h))
        conn.close.assert_called_once()
        self.assertEqual(res, body)


class fakeResponse:

    def __init__(self, body, status, reason = None):
        self.body = body
        self.status = status
        self.reason = reason

    def read(self):
        return self.body


if __name__ ==  "__main__":
    unittest.main()
