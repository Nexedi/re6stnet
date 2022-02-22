import sys
import os
import random
import string
import json
import httplib
import base64
import unittest
import subprocess
import hmac
import hashlib
import select
import time
from argparse import Namespace
from OpenSSL import crypto
from mock import Mock, patch
if 're6st' not in sys.modules:
    sys.path.append(os.path.dirname(sys.path[0]))
from re6st import registry


# TODO test for request_dump, requestToken, getNetworkConfig, getBoostrapPeer
# getIPV4Information, versions


def load_config(filename="registry.json"):
    with open(filename) as f:
        config = json.load(f)
    return Namespace(**config)


def generate_csr():
    """
    generate a certificate request file

    return: 
        crypto.Pekey and crypto.X509Req  both in pem format
    """
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)
    req = crypto.X509Req()
    req.set_pubkey(key)
    req.get_subject().CN = "test ca"
    req.sign(key, 'sha256')
    private_key = crypto.dump_privatekey(crypto.FILETYPE_PEM, key)
    csr = crypto.dump_certificate_request(crypto.FILETYPE_PEM, req)
    return private_key, csr


def get_cert(cur, prefix):
    res = cur.execute(
        "SELECT cert FROM cert WHERE prefix=?", (prefix,)).fetchone()
    return res[0]


def insert_cert(cur, ca, prefix, not_after=None, email=None):
    '''
        insert a cert to db
    '''
    key, csr = generate_csr()
    req = crypto.load_certificate_request(crypto.FILETYPE_PEM, csr)
    cert = crypto.X509()
    cert.gmtime_adj_notBefore(0)
    if not_after:
        cert.set_notAfter(
            time.strftime("%Y%m%d%H%M%SZ", time.gmtime(not_after)))
    else:
        cert.gmtime_adj_notAfter(registry.RegistryServer.cert_duration)

    subject = req.get_subject()
    subject.CN = prefix2cn(prefix)
    cert.set_subject(req.get_subject())
    cert.set_pubkey(req.get_pubkey())
    cert.set_serial_number(insert_cert.serial)
    insert_cert.serial += 1
    cert.sign(ca.key, 'sha512')
    cert = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
    cur.execute("INSERT INTO cert VALUES (?,?,?)", (prefix, email, cert))
    return key, cert

insert_cert.serial = 0


def delete_cert(cur, prefix):
    cur.execute("DELETE FROM cert WHERE prefix = ?", (prefix,))

# pkey: private key
def decrypt(pkey, incontent):
    with open("node.key", 'w') as f:
        f.write(pkey)
    args = "openssl rsautl -decrypt -inkey node.key".split()
    p = subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outcontent, err = p.communicate(incontent)
    return outcontent

def prefix2cn(prefix):
    return "%u/%u" % (int(prefix, 2), len(prefix))

# TODO function for get a unique prefix


class TestRegistrtServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # instance a server
        cls.config = load_config()
        cls.server = registry.RegistryServer(cls.config)


    @classmethod
    def tearDownClass(cls):
        # remove database
        try:
            os.unlink(cls.config.db)
        except e:
            pass


    def setUp(self):
        self.email = ''.join(random.sample(string.ascii_lowercase, 4)) \
            + "@mail.com"


    def test_recv(self):
        recv = self.server.sock.recv = Mock()
        recv.side_effect = [
            "0001001001001a_msg",
            "0001001001002\0001dqdq",
            "0001001001001\000a_msg",
            "0001001001001\000\4a_msg",
            "0000000000000\0" # ERROR, IndexError: msg is null
        ]

        res1 = self.server.recv(4)
        res2 = self.server.recv(4)
        res3 = self.server.recv(4)
        res4 = self.server.recv(4)

        self.assertEqual(res1, (None, None)) # not contain \0
        self.assertEqual(res2, (None, None)) # binary to digital failed
        self.assertEqual(res3, (None, None)) # code don't match
        self.assertEqual(res4, ("0001001001001", "a_msg"))

        del self.server.sock.recv


    def test_onTimeout(self):
        # old token, cert, not old token, cert
        # not after will equal to now -1
        # condtion prefix == self.prefix not covered
        cur = self.server.db.cursor()
        token_old, token = "bbbbdddd", "ddddbbbb"
        prefix_old, prefix = "1110", "1111"
        # 20 magic number, make sure we create old enough new cert/token
        now = int(time.time()) - registry.GRACE_PERIOD + 20
        # makeup data
        insert_cert(cur, self.server.cert, prefix_old, 1)
        insert_cert(cur, self.server.cert, prefix, now -1)
        cur.execute("INSERT INTO token VALUES (?,?,?,?)",
                    (token_old, self.email, 4, 2))
        cur.execute("INSERT INTO token VALUES (?,?,?,?)",
                    (token, self.email, 4, now))
        cur.close()

        self.server.onTimeout()

        self.assertIsNone(self.server.isToken(token_old))
        self.assertIsNotNone(self.server.isToken(token))
        cur = self.server.db.cursor()
        self.assertIsNone(get_cert(cur, prefix_old), "old cert not deleted")
        self.assertIsNotNone(get_cert(cur, prefix))
        self.assertEqual(self.server.timeout,
                         now - 1 + registry.GRACE_PERIOD,
                         "time_out set wrongly")


        delete_cert(cur, prefix)
        cur.close()
        self.server.deleteToken(token)


    @patch("re6st.registry.RegistryServer.func", Mock(), create=True)
    def test_handle_request(self):
        '''
            rpc with cn and have result
        '''
        prefix = "0000000011111111"
        method = "func"
        protocol = 7
        params = {"cn" : prefix, "a" : 1, "b" : 2}
        func = self.server.func
        func.getcallargs.return_value = params
        del func._private
        func.return_value = result = "this_is_a_result"
        key = "this_is_a_key"
        self.server.sessions[prefix] = [(key, protocol)]
        request = Mock()
        request.path = "/func?a=1&b=2&cn=0000000011111111"
        request.headers = {registry.HMAC_HEADER: base64.b64encode(
            hmac.HMAC(key, request.path, hashlib.sha1).digest())}

        self.server.handle_request(request, method, params)

        # hmac check
        key = hashlib.sha1(key).digest()
        self.assertEqual(self.server.sessions[prefix],
                         [(hashlib.sha1(key).digest(), protocol)])
        func.assert_called_once_with(**params)
        # http response check
        request.send_response.assert_called_once_with(httplib.OK)
        request.send_header.assert_any_call("Content-Length", str(len(result)))
        request.send_header.assert_any_call(
            registry.HMAC_HEADER,
            base64.b64encode(hmac.HMAC(key, result, hashlib.sha1).digest()))
        request.wfile.write.assert_called_once_with(result)

        # remove the create session \n
        del self.server.sessions[prefix]


    @patch("re6st.registry.RegistryServer.func", Mock(), create=True)
    def test_handle_request_private(self):
        """
            case request with _private attr
        """
        method = "func"
        params = {"a" : 1, "b" : 2}
        func = self.server.func
        func.getcallargs.return_value = params
        func.return_value = None
        request_good = Mock()
        request_good.client_address = self.config.authorized_origin
        request_good.headers = {'X-Forwarded-For':self.config.authorized_origin[0]}
        request_bad = Mock()
        request_bad.client_address = ["wrong_address"]

        self.server.handle_request(request_good, method, params)
        self.server.handle_request(request_bad, method, params)

        func.assert_called_once_with(**params)
        request_bad.send_error.assert_called_once_with(httplib.FORBIDDEN)
        request_good.send_response.assert_called_once_with(httplib.NO_CONTENT)


    # will cause valueError, if a node send hello twice to a registry
    def test_getPeerProtocol(self):
        prefix = "0000000011111110"
        insert_cert(self.server.db, self.server.cert, prefix)
        protocol = 7
        self.server.hello(prefix, protocol)
        # self.server.hello(prefix)

        res = self.server.getPeerProtocol(prefix)

        self.assertEqual(res, protocol)


    def test_hello(self):
        prefix = "0000000011111111"
        protocol = 7
        cur = self.server.db.cursor()
        pkey, _ = insert_cert(cur, self.server.cert, prefix)

        res = self.server.hello(prefix, protocol=protocol)

        # decrypt
        length = len(res)/2
        key, sign = res[:length], res[length:]
        key = decrypt(pkey, key)
        self.assertEqual(self.server.sessions[prefix][-1][0], key,
                         "different hmac key")
        self.assertEqual(self.server.sessions[prefix][-1][1], protocol)

        self.server.sessions[prefix][-1] = None
        delete_cert(cur, prefix)


    def test_addToken(self):
        # generate random token
        token_spec = "aaaabbbb"

        token = self.server.addToken(self.email, None)
        self.server.addToken(self.email, token_spec)

        self.assertIsNotNone(token)
        self.assertTrue(self.server.isToken(token))
        self.assertTrue(self.server.isToken(token_spec))

        # remove the affect of the function
        self.server.deleteToken(token)
        self.server.deleteToken(token_spec)


    def test_newPrefix(self):
        length = 16

        res = self.server.newPrefix(length)

        self.assertEqual(len(res), length)
        self.assertLessEqual(set(res), {'0', '1'}, "%s is not a binary" % res)

        # TODO test too many prefix


    @patch("re6st.registry.RegistryServer.createCertificate", Mock())
    def test_requestCertificate(self):
        token = self.server.addToken(self.email, None)
        fake_token = "aaaabbbb"
        _, csr = generate_csr()
        mmock = self.server.createCertificate

        # unvalide token
        self.server.requestCertificate(fake_token, csr)
        # valide token
        self.server.requestCertificate(token, csr)

        self.assertIsNone(self.server.isToken(token), "token not delete")
        mmock.assert_called_once()
        # check the call parameter
        prefix, subject, pubkey = mmock.call_args.args
        self.assertIsNotNone(subject.serialNumber)


    def test_requestCertificate_anoymous(self):
        _, csr = generate_csr()

        if self.config.anonymous_prefix_length is None:
            with self.assertRaises(registry.HTTPError):
                self.server.requestCertificate(None, csr)


    def test_getSubjectSerial(self):
        serial = self.server.getSubjectSerial()

        self.assertIsInstance(serial, int)
        # test the smallest unique possible
        nb_less = 0
        for cert in self.server.iterCert():
            s = cert[0].get_subject().serialNumber
            if(s and int(s) <= serial):
                nb_less += 1
        self.assertEqual(nb_less, serial)


    def test_createCertificate(self):
        _, csr = generate_csr()
        req = crypto.load_certificate_request(crypto.FILETYPE_PEM, csr)
        prefix = "00011111101001110"
        subject = req.get_subject()
        subject.serialNumber = str(self.server.getSubjectSerial())
        self.server.db.execute("INSERT INTO cert VALUES (?,null,null)", (prefix,))

        cert = self.server.createCertificate(prefix, subject, req.get_pubkey())

        cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert)
        self.assertEqual(cert.get_subject().CN, prefix2cn(prefix))
        self.assertEqual(cert.get_serial_number(), self.server.getConfig('serial', 0))
        self.assertIsNotNone(get_cert(self.server.db, prefix))


    @patch("re6st.registry.RegistryServer.createCertificate", Mock())
    def test_renewCertificate(self):
        # TODO condition crl
        mmock = self.server.createCertificate
        cur = self.server.db.cursor()
        prefix_old = "11111"
        prefix_new = "11110"
        insert_cert(cur, self.server.cert, prefix_old, 1)
        _, cert_new = insert_cert(cur, self.server.cert, prefix_new,
                                  time.time() + 2 * registry.RENEW_PERIOD)
        cur.close()

        # need renew
        self.server.renewCertificate(prefix_old)
        # no need renew
        res_new = self.server.renewCertificate(prefix_new)

        prefix, subject, pubkey, not_after = mmock.call_args.args
        self.assertEqual(prefix, prefix_old)
        self.assertEqual(not_after, None)
        self.assertEqual(res_new, cert_new)

        cur = self.server.db.cursor()
        delete_cert(cur, prefix_old)
        delete_cert(cur, prefix_new)
        cur.close()


    @patch("re6st.registry.RegistryServer.recv", Mock())
    @patch("select.select", Mock(return_value=[1]))
    def test_queryAddress(self):
        recv = self.server.recv
        prefix = "000100100010001"
        # one bad, one correct prefix
        recv.side_effect = [("0", "a msg"), (prefix, "other msg")]

        res = self.server._queryAddress(prefix)

        self.assertEqual(res, "other msg")


    @patch('re6st.registry.RegistryServer.updateNetworkConfig', Mock())
    def test_revoke(self):
        # case: no ValueError
        serial = insert_cert.serial
        prefix = bin(serial)[2:].rjust(16, '0') # length 16 prefix
        insert_cert(self.server.db, self.server.cert, prefix)

        self.server.revoke(serial)
        # ValueError if serial correspond cert not exist

        self.server.updateNetworkConfig.assert_called_once()


    @patch('re6st.registry.RegistryServer.updateNetworkConfig', Mock())
    def test_revoke_value(self):
        # case: ValueError
        serial = insert_cert.serial
        prefix = bin(serial)[2:].rjust(16, '0') # length 16 prefix
        insert_cert(self.server.db, self.server.cert, prefix, 1)
        self.server.sessions.setdefault(prefix, "something")

        self.server.revoke("%u/16" % serial) # 16 is length

        self.assertIsNone(self.server.sessions.get(prefix))
        self.assertIsNone(get_cert(self.server.db, prefix))


    def test_updateHMAC(self):
        def get_hmac():
            return [self.server.getConfig(registry.BABEL_HMAC[i], None)
                    for i in range(3)]

        for i in range(3):
            self.server.delHMAC(i)

        # step 1
        self.server.updateHMAC()

        hmacs = get_hmac()
        key_1 = hmacs[1]
        self.assertEqual(hmacs, [None, key_1, ''])

        # step 2
        self.server.updateHMAC()

        self.assertEqual(get_hmac(), [key_1, None, None])

        # step 3
        self.server.updateHMAC()

        hmacs = get_hmac()
        key_2 = hmacs[1]
        self.assertEqual(get_hmac(), [key_1, key_2, None])

        # step 4
        self.server.updateHMAC()

        self.assertEqual(get_hmac(), [None, key_2, key_1])


    def test_getNodePrefix(self):
        # prefix in short format
        prefix = "0000000101"
        insert_cert(self.server.db, self.server.cert, prefix, email=self.email)

        res = self.server.getNodePrefix(self.email)

        self.assertEqual(res, "%u/%u" % (int(prefix, 2), len(prefix)))


    @patch("select.select", Mock())
    @patch("re6st.registry.RegistryServer.recv", Mock())
    @patch("re6st.registry.RegistryServer.sendto", Mock())
    # use case which recored form demo
    def test_topology(self):
        recv = self.server.recv
        sendto = self.server.sendto
        recv_case = [
            ('0000000000000000', '2 6/16 7/16 1/16 3/16 36893488147419103232/80 4/16'),
            ('00000000000000100000000000000000000000000000000000000000000000000000000000000000', '2 0/16 7/16'),
            ('0000000000000011', '2 0/16 7/16'),
            ('0000000000000111', '2 4/16 6/16 0/16 3/16 36893488147419103232/80'),
            ('0000000000000111', '2 4/16 6/16 0/16 3/16 36893488147419103232/80'),
            ('0000000000000001', '2 0/16 6/16')
        ]
        recv.side_effect = recv_case
        def side_effct(rlist, wlist, elist, timeout):
            # rlist is true until the len(recv_case)th call
            side_effct.i -= side_effct.i > 0
            return [side_effct.i, wlist, None]
        side_effct.i = len(recv_case) + 1
        select.select.side_effect = side_effct

        res = self.server.topology()

        expect_res = '{"36893488147419103232/80": ["0/16", "7/16"], "": ["36893488147419103232/80", "3/16", "1/16", "0/16", "7/16"], "4/16": ["0/16"], "3/16": ["0/16", "7/16"], "0/16": ["6/16", "7/16"], "1/16": ["6/16", "0/16"], "7/16": ["6/16", "4/16"]}'
        self.assertEqual(res, expect_res)


if __name__ == "__main__":
    unittest.main()
