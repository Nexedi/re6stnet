#!/usr/bin/env python
from OpenSSL import crypto
import argparse, os, xmlrpclib

def main():
    parser = argparse.ArgumentParser(
            description='Setup script for vifib')
    _ = parser.add_argument
    _('--server', required=True,
            help='Address of the server delivering certifiactes')
    _('--port', required=True, type=int,
            help='Port to which connect on the server')
    _('-d', '--dir', default='/etc/vifib',
            help='Directory where the key and certificate will be stored')
    _('-r', '--req', nargs='+',
            help='''Certificate request additional arguments. For example :
                  --req name1 value1 name2 value2, to add attributes name1 and name2''')
    config = parser.parse_args()
    if config.req and len(config.req) % 2 == 1:
        print "Sorry, request argument was incorrect, there must be an even number of request arguments"
        os.exit(1)

    # Get token
    email = raw_input('Please enter your email address : ')
    s = xmlrpclib.ServerProxy('http://%s:%u' % (config.server, config.port))
    _ = s.requestToken(email)
    token = raw_input('Please enter your token : ')

    # Generate key and cert request
    pkey = crypto.PKey()
    pkey.generate_key(crypto.TYPE_RSA, 2048)
    key = crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey)

    req = crypto.X509Req()
    subj = req.get_subject()
    if config.req:
        while len(config.req) > 1:
            key = config.req.pop(0)
            value = config.req.pop(0)
            setattr(subj, key, value)
    req.set_pubkey(pkey)
    req.sign(pkey, 'sha1')
    req = crypto.dump_certificate_request(crypto.FILETYPE_PEM, req)

    # Get certificates
    ca = s.getCa()
    cert = s.requestCertificate(token,req)

    # Store cert and key
    with open(os.path.join(config.dir, 'cert.key'), 'w') as f:
        f.write(key)
    with open(os.path.join(config.dir, 'cert.crt'), 'w') as f:
        f.write(cert)
    with open(os.path.join(config.dir, 'ca.pem'), 'w') as f:
        f.write(ca)

    print "Certificate setup complete."

if __name__ == "__main__":
    main()
