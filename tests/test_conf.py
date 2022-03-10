#!/usr/bin/python2
""" unit test for re6st-conf
"""

import os
import sys
import unittest
from shutil import rmtree
from StringIO import StringIO
from mock import patch

if 're6st' not in sys.modules:
    sys.path.append(os.path.dirname(sys.path[0]))
from re6st.cli import conf
from tools import generate_cert, serial2prefix


# gloable value from conf.py
conf_path = 're6stnet.conf'
ca_path = 'ca.crt'
cert_path = 'cert.crt'
key_path = 'cert.key'

# TODO test for is needed

class TestConf(unittest.TestCase):
    """ Unit test case for re6st-conf
    """

    @classmethod
    def setUpClass(cls):
        # because conf will change directory
        cls.origin_dir = os.getcwd()
        cls.work_dir = "temp"

        if not os.path.exists(cls.work_dir):
            os.makedirs(cls.work_dir)

        # mocked service cert and pkey
        with open("root.crt") as f:
            cls.cert = f.read()
        with open("registry.key") as f:
            cls.pkey = f.read()

        cls.command = "re6st-conf --registry http://localhost/" \
            " --dir %s" % cls.work_dir

        cls.serial = 0

        cls.stdout = sys.stdout
        cls.null = open(os.devnull, 'w')
        sys.stdout = cls.null


    @classmethod
    def tearDownClass(cls):
        # remove work directory
        rmtree(cls.work_dir)
        cls.null.close()
        sys.stdout = cls.stdout


    def setUp(self):
        patcher = patch("re6st.registry.RegistryClient")
        self.addCleanup(patcher.stop)
        self.client = patcher.start()()

        self.client.getCa.return_value = self.cert
        prefix = serial2prefix(self.serial)
        self.client.requestCertificate.side_effect = \
            lambda _, req: generate_cert(self.pkey, req, prefix, self.serial)
        self.serial += 1


    def tearDown(self):
        # go back to original dir
        os.chdir(self.origin_dir)


    @patch("__builtin__.raw_input")
    def test_basic(self, mock_raw_input):
        """ go through all the step
            getCa, requestToken, requestCertificate
        """
        mail = "example@email.com"
        token = "a_token"
        mock_raw_input.side_effect = [mail, token]
        command = self.command \
            + " --fingerprint sha1:a1861330f1299b98b529fa52c3d8e5d1a94dc63a" \
            + " --req L lille"
        sys.argv = command.split()

        conf.main()

        self.client.requestToken.assert_called_once_with(mail)
        self.assertEqual(self.client.requestCertificate.call_args.args[0],
                         token)
        # created file part
        self.assertTrue(os.path.exists(ca_path))
        self.assertTrue(os.path.exists(key_path))
        self.assertTrue(os.path.exists(cert_path))
        self.assertTrue(os.path.exists(conf_path))


    def test_fingerprint_mismatch(self):
        """ wrong fingerprint with same size,
        """
        command = self.command \
            + " --fingerprint sha1:a1861330f1299b98b529fa52c3d8e5d1a94dc000"
        sys.argv = command.split()

        with self.assertRaises(SystemExit) as e:
            conf.main()

        self.assertIn("fingerprint doesn't match", str(e.exception))


    def test_ca_only(self):
        """ only create ca file and exit
        """
        command = self.command + " --ca-only"
        sys.argv = command.split()

        with self.assertRaises(SystemExit):
            conf.main()

        self.assertTrue(os.path.exists(ca_path))


    def test_anonymous(self):
        """ with args anonymous, so script will use '' as token
        """
        command = self.command + " --anonymous"
        sys.argv = command.split()

        conf.main()

        self.assertEqual(self.client.requestCertificate.call_args.args[0],
                         '')


    def test_anonymous_failed(self):
        """ with args anonymous and token, so script will failed
        """
        command = self.command + " --anonymous" \
            + " --token a"
        sys.argv = command.split()
        text = StringIO()
        old_err = sys.stderr
        sys.stderr = text

        with self.assertRaises(SystemExit):
            conf.main()

        # check the error message
        self.assertIn("anonymous conflicts", text.getvalue())

        sys.stderr = old_err


    def test_req_reserved(self):
        """ with args req, but contain reserved value
        """
        command = self.command + " --req CN 1111"
        sys.argv = command.split()

        with self.assertRaises(SystemExit) as e:
            conf.main()

        self.assertIn("CN field", str(e.exception))


    def test_get_null_cert(self):
        """ simulate fake token, and get null cert
        """
        command = self.command + " --token a"
        sys.argv = command.split()
        self.client.requestCertificate.side_effect = "",

        with self.assertRaises(SystemExit) as e:
            conf.main()

        self.assertIn("invalid or expired token", str(e.exception))


if __name__ == "__main__":
    unittest.main()
        