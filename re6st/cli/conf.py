#!/usr/bin/env python3
import argparse, atexit, hashlib, inspect, os, subprocess, sqlite3, sys, time
from datetime import timedelta
if 're6st' not in sys.modules:
    sys.path[0] = os.path.dirname(os.path.dirname(sys.path[0]))
from cryptography import x509 as cx509
from cryptography.hazmat.primitives.serialization import \
    Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ObjectIdentifier
from re6st import registry, utils, x509

NAME_OIDS = {
    v._name: v
    for k, v in inspect.getmembers(NameOID)
    if isinstance(v, ObjectIdentifier)
}
# BBB: cryptography < 37 does not have _NAME_TO_NAMEOID
from cryptography.x509.name import _NAMEOID_TO_NAME
NAME_OIDS.update((v, k) for k, v in _NAMEOID_TO_NAME.items())

def create(path, text=None, mode=0o666):
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, mode)
    try:
        os.write(fd, text)
    finally:
        os.close(fd)

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
    _('--location',
            help="Alpha-2 codes of country and continent separated by a comma."
                 " Will be used for the community assignment (default: location"
                 " is automatically detected). Example: FR,EU")
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
    ca = x509.load_pem_x509_certificate(s.getCa())
    if config.fingerprint:
        try:
            alg, fingerprint = config.fingerprint.split(':', 1)
            fingerprint = bytes.fromhex(fingerprint)
            if hashlib.new(alg).digest_size != len(fingerprint):
                raise ValueError("wrong size")
        except Exception as e:
            parser.error("invalid fingerprint: %s" % e)
        if fingerprint != hashlib.new(
                alg, ca.public_bytes(Encoding.DER)).digest():
            sys.exit("CA fingerprint doesn't match")
    else:
        print("WARNING: it is strongly recommended to use --fingerprint option.")
    network = x509.networkFromCa(ca)
    if config.is_needed:
        with subprocess.Popen(('ip', '-6', '-o', 'route', 'get',
                               utils.ipFromBin(network)),
                              stdout=subprocess.PIPE) as proc:
            route, err = proc.communicate()
        sys.exit(err or route and
            utils.binFromIp(route.split()[8]).startswith(network))

    create(ca_path, ca.public_bytes(Encoding.PEM))
    if config.ca_only:
        sys.exit()

    reserved = 'commonName', 'serialNumber'
    try:
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        attrs = {x.oid._name: x for x in cert.subject}
        for k in reserved:
            attrs.pop(k, None)
    except FileNotFoundError:
        attrs = {}
    for k, v in config.req or ():
        try:
            x = NAME_OIDS[k]
        except KeyError:
            raise ValueError("Unknown subject attribute: " + k)
        k = x._name
        if k in reserved:
            sys.exit(k + " field is reserved.")
        attrs[k] = cx509.NameAttribute(x, v)

    cert_fd = token_advice = None
    try:
        token = config.token
        if config.anonymous:
            if not (token is config.email is None):
                parser.error("--anonymous conflicts with --email/--token")
            token = ''
        elif not token:
            if not config.email:
                config.email = input('Please enter your email address: ')
            s.requestToken(config.email)
            token_advice = "Use --token to retry without asking a new token\n"
            while not token:
                token = input('Please enter your token: ')

        try:
            with open(key_path, 'rb') as f:
                pkey = x509.load_pem_private_key(f.read(), password=None)
            print("Reusing existing key.")
        except FileNotFoundError:
            bits = ca.public_key().key_size
            print("Generating %s-bit key ..." % bits)
            pkey = rsa.generate_private_key(65537, bits, backend=x509.backend)
            key = pkey.private_bytes(
                Encoding.PEM,
                PrivateFormat.TraditionalOpenSSL,
                NoEncryption())
            create(key_path, key, 0o600)

        csr = cx509.CertificateSigningRequestBuilder(
            subject_name=cx509.Name(attrs.values()),
        ).sign(pkey, hashes.SHA512(), backend=x509.backend)
        req = csr.public_bytes(Encoding.PEM)

        # First make sure we can open certificate file for writing,
        # to avoid using our token for nothing.
        cert_fd = os.open(cert_path, os.O_CREAT | os.O_WRONLY, 0o666)
        print("Requesting certificate ...")
        if config.location:
            cert = s.requestCertificate(token, req, location=config.location)
        else:
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

    cert = x509.load_pem_x509_certificate(cert)
    not_after = x509.notAfterDT(cert)
    print("Setup complete. Certificate is valid until %s UTC"
          " and will be automatically renewed after %s UTC.\n"
          "Do not forget to backup to your private key (%s) or"
          " you will lose your assigned subnet." % (
        not_after.ctime(),
        (not_after - timedelta(seconds=registry.RENEW_PERIOD)).ctime(),
        key_path))

    if not os.path.lexists(conf_path):
        create(conf_path, ("""\
registry %s
ca %s
cert %s
key %s
%s
# increase re6stnet verbosity:
#verbose 3
# enable OpenVPN logging:
#ovpnlog
# uncomment the following 2 lines to increase OpenVPN verbosity:
#O--verb
#O3
""" % (config.registry, ca_path, cert_path, key_path,
       ('country ' + config.location.split(',', 1)[0])
           if config.location else '')).encode())
        print("Sample configuration file created.")

    cn = x509.subnetFromCert(cert)
    subnet = network + utils.binFromSubnet(cn)
    print("Your subnet: %s/%u (CN=%s)"
        % (utils.ipFromBin(subnet), len(subnet), cn))

if __name__ == "__main__":
    main()
