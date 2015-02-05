import calendar, logging, os, subprocess, threading, time
from OpenSSL import crypto
from . import utils

def networkFromCa(ca):
    return bin(ca.get_serial_number())[3:]

def subnetFromCert(cert):
    return cert.get_subject().CN

def notAfter(cert):
    return calendar.timegm(time.strptime(cert.get_notAfter(),'%Y%m%d%H%M%SZ'))

def openssl(*args):
    return utils.Popen(('openssl',) + args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

def encrypt(cert, data):
    r, w = os.pipe()
    try:
        threading.Thread(target=os.write, args=(w, cert)).start()
        p = openssl('rsautl', '-encrypt', '-certin',
                    '-inkey', '/proc/self/fd/%u' % r)
        out, err = p.communicate(data)
    finally:
        os.close(r)
        os.close(w)
    if p.returncode:
        raise subprocess.CalledProcessError(p.returncode, 'openssl', err)
    return out

def maybe_renew(path, cert, info, renew):
    from .registry import RENEW_PERIOD
    while True:
        next_renew = notAfter(cert) - RENEW_PERIOD
        if time.time() < next_renew:
            return cert, next_renew
        try:
            pem = renew()
            if not pem or pem == crypto.dump_certificate(
                  crypto.FILETYPE_PEM, cert):
                exc_info = 0
                break
            cert = crypto.load_certificate(crypto.FILETYPE_PEM, pem)
        except Exception:
            exc_info = 1
            break
        new_path = path + '.new'
        with open(new_path, 'w') as f:
            f.write(pem)
        try:
            s = os.stat(path)
            os.chown(new_path, s.st_uid, s.st_gid)
        except OSError:
            pass
        os.rename(new_path, path)
        logging.info("%s renewed until %s UTC",
            info, time.asctime(time.gmtime(notAfter(cert))))
    logging.error("%s not renewed. Will retry tomorrow.",
                  info, exc_info=exc_info)
    return cert, time.time() + 86400

class VerifyError(Exception):
    pass

class Cert(object):

    def __init__(self, ca, key, cert=None):
        self.ca_path = ca
        self.cert_path = cert
        self.key_path = key
        with open(ca) as f:
            self.ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        with open(key) as f:
            self.key = crypto.load_privatekey(crypto.FILETYPE_PEM, f.read())
        if cert:
            with open(cert) as f:
                cert = f.read()
            self.cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert)

    @property
    def prefix(self):
        return utils.binFromSubnet(subnetFromCert(self.cert))

    @property
    def network(self):
        return networkFromCa(self.ca)

    @property
    def openvpn_args(self):
        return ('--ca', self.ca_path,
                '--cert', self.cert_path,
                '--key', self.key_path)

    def maybeRenew(self, registry):
        from .registry import RegistryClient
        registry = RegistryClient(registry, self)
        self.cert, next_renew = maybe_renew(self.cert_path, self.cert,
              "Certificate", lambda: registry.renewCertificate(self.prefix))
        self.ca, ca_renew = maybe_renew(self.ca_path, self.ca,
              "CA Certificate", registry.getCa)
        return min(next_renew, ca_renew)

    def verify(self, sign, data):
        crypto.verify(self.ca, sign, data, 'sha1')

    def sign(self, data):
        return crypto.sign(self.key, data, 'sha1')

    def decrypt(self, data):
        p = openssl('rsautl', '-decrypt', '-inkey', self.key_path)
        out, err = p.communicate(data)
        if p.returncode:
            raise subprocess.CalledProcessError(p.returncode, 'openssl', err)
        return out
