#!/usr/bin/env python
import argparse, os, subprocess, sqlite3, sys, xmlrpclib
from OpenSSL import crypto

def main():
    parser = argparse.ArgumentParser(
            description='Setup script for vifib')
    _ = parser.add_argument
    _('--ca-only', action='store_true',
            help='To only get CA form server')
    _('--db-only', action='store_true',
            help='To only get CA and setup peer db with bootstrap peer')
    _('--no-boot', action='store_true',
            help='Enable to skip getting bootstrap peer')
    _('--server', required=True,
            help='Address of the server delivering certifiactes')
    _('--port', required=True, type=int,
            help='Port to which connect on the server')
    _('-d', '--dir', default='/etc/vifib',
            help='Directory where the key and certificate will be stored')
    _('-r', '--req', nargs=2, action='append',
            help='Name and value of certificate request additional arguments')
    _('--email', help='Your email address')
    _('--token', help='The token you received')
    config = parser.parse_args()

    # Establish connection with server
    s = xmlrpclib.ServerProxy('http://%s:%u' % (config.server, config.port))

    # Get CA
    ca = s.getCa()
    with open(os.path.join(config.dir, 'ca.pem'), 'w') as f:
        f.write(ca)

    if config.ca_only:
        sys.exit(0)

    # Get token
    if not config.token:
        if not config.email:
            config.email = raw_input('Please enter your email address : ')
        _ = s.requestToken(config.email)
        config.token = raw_input('Please enter your token : ')

    # Generate key and cert request
    pkey = crypto.PKey()
    pkey.generate_key(crypto.TYPE_RSA, 2048)
    key = crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey)

    req = crypto.X509Req()
    subj = req.get_subject()
    if config.req:
        for arg in config.req:
            setattr(subj, arg[0], arg[1])
    req.set_pubkey(pkey)
    req.sign(pkey, 'sha1')
    req = crypto.dump_certificate_request(crypto.FILETYPE_PEM, req)

    # Get certificate
    cert = s.requestCertificate(config.token, req)

    # Store cert and key
    with open(os.path.join(config.dir, 'cert.key'), 'w') as f:
        f.write(key)
    with open(os.path.join(config.dir, 'cert.crt'), 'w') as f:
        f.write(cert)

    # Generating dh file
    if not os.access(os.path.join(config.dir, 'dh2048.pem'), os.F_OK):
       subprocess.call(['openssl', 'dhparam', '-out', os.path.join(config.dir, 'dh2048.pem'), '2048'])

    print "Certificate setup complete."

if __name__ == "__main__":
    main()
