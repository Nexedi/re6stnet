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
    config = parser.parse_args()

    # Establish connection with server
    s = xmlrpclib.ServerProxy('http://%s:%u' % (config.server, config.port))

    # Get CA
    ca = s.getCa()
    with open(os.path.join(config.dir, 'ca.pem'), 'w') as f:
        f.write(ca)

    if config.ca_only:
        sys.exit(0)

    # Create and initialize peers DB
    db = sqlite3.connect(os.path.join(config.dir, 'peers.db'), isolation_level=None)
    try:
        db.execute("""CREATE TABLE peers (
                   prefix TEXT PRIMARY KEY,
                   address TEXT NOT NULL,
                   used INTEGER NOT NULL DEFAULT 0,
                   date INTEGER DEFAULT (strftime('%s', 'now')))""")
        db.execute("CREATE INDEX _peers_used ON peers(used)")
        if not config.no_boot:
            prefix, address = s.getBootstrapPeer()
            db.execute("INSERT INTO peers (prefix, address) VALUES (?,?)", (prefix, address))
    except sqlite3.OperationalError, e:
        if e.args[0] == 'table peers already exists':
            print "Table peers already exists, leaving it as it is"
        else:
            print "sqlite3.OperationalError :" + e.args[0]
            sys.exit(1)

    if config.db_only:
        sys.exit(0)

    # Get token
    email = raw_input('Please enter your email address : ')
    _ = s.requestToken(email)
    token = raw_input('Please enter your token : ')

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
    cert = s.requestCertificate(token, req)

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
