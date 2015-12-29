#!/usr/bin/python2
import argparse, atexit, binascii, errno, hashlib
import os, subprocess, sqlite3, sys, time
from OpenSSL import crypto
if 're6st' not in sys.modules:
    sys.path[0] = os.path.dirname(os.path.dirname(sys.path[0]))
from re6st import registry, utils, x509

def create(path, text=None, mode=0666):
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, mode)
    try:
        os.write(fd, text)
    finally:
        os.close(fd)

def loadCert(pem):
    return crypto.load_certificate(crypto.FILETYPE_PEM, pem)

def main():
    parser = argparse.ArgumentParser(
        description="Setup script for re6stnet.",
        formatter_class=utils.HelpFormatter)
    _ = parser.add_argument
    _('--fingerprint', metavar='ALG:FINGERPRINT',
        help="Check CA fingerprint to protect against MITM.")
    _('--registry', required=True, metavar='URL',
        help="HTTP URL of the server delivering certificates.")
    _('--is-needed', action='store_true',
        help="Exit immediately after asking the registry CA. Status code is"
             " non-zero if we're already part of the network, which means"
             " re6st is already running or we're behind a re6st router.")
    _('--ca-only', action='store_true',
        help='Only fetch CA from registry and exit.')
    _('-d', '--dir',
        help="Directory where the key and certificate will be stored.")
    _('-r', '--req', nargs=2, action='append', metavar=('KEY', 'VALUE'),
        help="The registry only sets the Common Name of your certificate,"
             " which actually encodes your allocated prefix in the network."
             " You can repeat this option to add any field you want to its"
             " subject.")
    _('--email',
        help="Email address where your token is sent. Use -r option if you"
             " want to show an email in your certificate.")
    _('--token', help="The token you received.")
    _('--anonymous', action='store_true',
        help="Request an anonymous certificate. No email is required but the"
             " registry may deliver a longer prefix.")
    config = parser.parse_args()
    if config.dir:
        os.chdir(config.dir)
    conf_path = 're6stnet.conf'
    ca_path = 'ca.crt'
    cert_path = 'cert.crt'
    key_path = 'cert.key'

    # Establish connection with server
    s = registry.RegistryClient(config.registry)

    # Get CA
    ca = loadCert(s.getCa())
    if config.fingerprint:
        try:
            alg, fingerprint = config.fingerprint.split(':', 1)
            fingerprint = binascii.a2b_hex(fingerprint)
            if hashlib.new(alg).digest_size != len(fingerprint):
                raise ValueError("wrong size")
        except StandardError, e:
            parser.error("invalid fingerprint: %s" % e)
        if x509.fingerprint(ca, alg).digest() != fingerprint:
            sys.exit("CA fingerprint doesn't match")
    else:
        print "WARNING: it is strongly recommended to use --fingerprint option."
    network = x509.networkFromCa(ca)
    if config.is_needed:
        route, err = subprocess.Popen(('ip', '-6', '-o', 'route', 'get',
                                       utils.ipFromBin(network)),
                                      stdout=subprocess.PIPE).communicate()
        sys.exit(err or route and
            utils.binFromIp(route.split()[8]).startswith(network))

    create(ca_path, crypto.dump_certificate(crypto.FILETYPE_PEM, ca))
    if config.ca_only:
        sys.exit()

    reserved = 'CN', 'serial'
    req = crypto.X509Req()
    try:
        with open(cert_path) as f:
            cert = loadCert(f.read())
        components = dict(cert.get_subject().get_components())
        for k in reserved:
            components.pop(k, None)
    except IOError, e:
        if e.errno != errno.ENOENT:
            raise
        components = {}
    if config.req:
        components.update(config.req)
    subj = req.get_subject()
    for k, v in components.iteritems():
        if k in reserved:
            sys.exit(k + " field is reserved.")
        if v:
            setattr(subj, k, v)

    cert_fd = token_advice = None
    try:
        token = config.token
        if config.anonymous:
            if not (token is config.email is None):
                parser.error("--anonymous conflicts with --email/--token")
            token = ''
        elif not token:
            if not config.email:
                config.email = raw_input('Please enter your email address: ')
            s.requestToken(config.email)
            token_advice = "Use --token to retry without asking a new token\n"
            while not token:
                token = raw_input('Please enter your token: ')

        try:
            with open(key_path) as f:
                pkey = crypto.load_privatekey(crypto.FILETYPE_PEM, f.read())
            key = None
            print "Reusing existing key."
        except IOError, e:
            if e.errno != errno.ENOENT:
                raise
            bits = ca.get_pubkey().bits()
            print "Generating %s-bit key ..." % bits
            pkey = crypto.PKey()
            pkey.generate_key(crypto.TYPE_RSA, bits)
            key = crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey)
            create(key_path, key, 0600)

        req.set_pubkey(pkey)
        req.sign(pkey, 'sha512')
        req = crypto.dump_certificate_request(crypto.FILETYPE_PEM, req)

        # First make sure we can open certificate file for writing,
        # to avoid using our token for nothing.
        cert_fd = os.open(cert_path, os.O_CREAT | os.O_WRONLY, 0666)
        print "Requesting certificate ..."
        cert = s.requestCertificate(token, req)
        if not cert:
            token_advice = None
            sys.exit("Error: invalid or expired token")
    except:
        if cert_fd is not None and not os.lseek(cert_fd, 0, os.SEEK_END):
            os.remove(cert_path)
        if token_advice:
            atexit.register(sys.stdout.write, token_advice)
        raise
    os.write(cert_fd, cert)
    os.ftruncate(cert_fd, len(cert))
    os.close(cert_fd)

    cert = loadCert(cert)
    not_after = x509.notAfter(cert)
    print("Setup complete. Certificate is valid until %s UTC"
          " and will be automatically renewed after %s UTC.\n"
          "Do not forget to backup to your private key (%s) or"
          " you will lose your assigned subnet." % (
        time.asctime(time.gmtime(not_after)),
        time.asctime(time.gmtime(not_after - registry.RENEW_PERIOD)),
        key_path))

    if not os.path.lexists(conf_path):
        create(conf_path, """\
registry %s
ca %s
cert %s
key %s
# increase re6stnet verbosity:
#verbose 3
# enable OpenVPN logging:
#ovpnlog
# increase OpenVPN verbosity:
#O--verb
#O3
""" % (config.registry, ca_path, cert_path, key_path))
        print "Sample configuration file created."

    cn = x509.subnetFromCert(cert)
    subnet = network + utils.binFromSubnet(cn)
    print "Your subnet: %s/%u (CN=%s)" \
        % (utils.ipFromBin(subnet), len(subnet), cn)

if __name__ == "__main__":
    main()
