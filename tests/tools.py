import sys
import os
import time
import subprocess
from OpenSSL import crypto

if 're6st' not in sys.modules:
    sys.path.append(os.path.dirname(sys.path[0]))
from re6st import registry

def generate_csr():
    """
    generate a certificate request

    return: 
        crypto.Pekey and crypto.X509Req  both in pem format
    """
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)
    req = crypto.X509Req()
    req.set_pubkey(key)
    req.get_subject().CN = "test ca"
    req.sign(key, 'sha256')
    pkey = crypto.dump_privatekey(crypto.FILETYPE_PEM, key)
    csr = crypto.dump_certificate_request(crypto.FILETYPE_PEM, req)
    return pkey, csr


def generate_cert(ca_key, csr, prefix, serial, not_after=None):
    """generate a certificate

    return 
        crypto.X509Cert in pem format
    """
    if type(ca_key) is str:
        ca_key = crypto.load_privatekey(crypto.FILETYPE_PEM, ca_key)
    req = crypto.load_certificate_request(crypto.FILETYPE_PEM, csr)
    cert = crypto.X509()
    cert.gmtime_adj_notBefore(0)
    if not_after:
        cert.set_notAfter(
            time.strftime("%Y%m%d%H%M%SZ", time.gmtime(not_after)))
    else:
        cert.gmtime_adj_notAfter(registry.RegistryServer.cert_duration)
    subject = req.get_subject()
    if prefix:
        subject.CN = prefix2cn(prefix)
    cert.set_subject(req.get_subject())
    cert.set_pubkey(req.get_pubkey())
    cert.set_serial_number(serial)
    cert.sign(ca_key, 'sha512')
    cert = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)

    return cert


def prefix2cn(prefix):
    return "%u/%u" % (int(prefix, 2), len(prefix))

def serial2prefix(serial):
    return bin(serial)[2:].rjust(16, '0') 

# pkey: private key
def decrypt(pkey, incontent):
    with open("node.key", 'w') as f:
        f.write(pkey)
    args = "openssl rsautl -decrypt -inkey node.key".split()
    p = subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outcontent, err = p.communicate(incontent)
    return outcontent
