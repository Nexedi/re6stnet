#!/usr/bin/env python
import argparse, math, random, smtplib, sqlite3
from email.mime.text import MIMEText
from SimpleXMLRPCServer import SimpleXMLRPCServer
from OpenSSL import crypto
import netaddr

class main(object):

    def __init__(self):
        self.cert_duration = 365 * 86400

        # Command line parsing
        parser = argparse.ArgumentParser(
                description='Peer discovery http server for vifibnet')
        _ = parser.add_argument
        _('--db', required=True,
                help='Path to database file')
        _('--ca', required=True,
                help='Path to ca.crt file')
        _('--key', required=True,
                help='Path to certificate key')
        config = parser.parser_arg()

        # Database initializing
        self.db = sqlite3.connect(config.db, isolation_level=None)
        self.db.execute("""CREATE TABLE IF NOT EXISTS tokens (
                        token text primary key not null,
                        email text not null,
                        prefix_len integer not null default 16,
                        date integer not null)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS vifib (
                        prefix text primary key not null,
                        email text,
                        cert text)""")

        # Loading certificates
        with open(config.ca) as f:
            self.ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        with open(config.key) as f:
            self.key = crypto.load_privatekey(crypto.FILETYPE_PEM, f.read())
        # Get vifib network prefix
        self.network = bin(self.ca.get_serial())[3:]

        # Starting server
        server = SimpleXMLRPCServer(("localhost", 8000))
        server.register_instance(self)
        server.serve_forever()

    def requestToken(self, email):
        while True:
            # Generating token
            token = ''.join(random.sample(string.ascii_lowercase, 8))
            # Updating database
            try:
                self.db.execute("INSERT INTO tokens (?,?,null,?)", (token, email, int(time.time())))
                break
            except sqlite3.IntegrityError, e:
                pass

        # Creating and sending email
        s = smtplib.SMTP('localhost')
        me = 'postmaster@vifibnet.com'
        msg = MIMEText('Hello world !\nYour token : %s' % (token,))
        msg['Subject'] = '[Vifibnet] Token Request'
        msg['From'] = me
        msg['To'] = email
        s.sendmail(me, email, msg.as_string())
        s.quit()

    def _getPrefix(self, prefix_len):
        assert 0 < prefix_len <= 128 - len(self.network)
        for prefix in self.db.execute("""SELECT prefix FROM vifib WHERE length(prefix) <= ? AND cert is null
                                         ORDER BY length(prefix) DESC""", (prefix_len,)):
            while len(prefix) < prefix_len:
                self.db.execute("UPDATE vifib SET prefix = ? WHERE prefix = ?", (prefix + '1', prefix))
                prefix += '0'
                self.db.execute("INSERT INTO vifib VALUES (?,null,null)", (prefix,))
            return prefix
        raise RuntimeError # TODO: raise better exception

    def requestCertificate(self, token, cert_req):
        req = crypto.load_certificate_request(crypto.FILETYPE_PEM, cert_req)
        with self.db:
            try:
                token, email, prefix_len, _ = self.db.execute("SELECT * FROM tokens WHERE token = ?", (token,)).next()
            except StopIteration:
                # TODO: return nice error message
                raise
            self.db.execute("DELETE FROM tokens WHERE token = ?", (token,))

            # Get a new prefix
            prefix = self._getPrefix(prefix_len)

            # Get complete ipv6 address from prefix
            #ip = hex(int(prefix.ljust(80, '0'),2))[2::] # XXX: do not hardcode
            #ip6 = self.vifib
            #for i in xrange(0, len(ip), 4):
            #    ip6 += ip[i:i+4] + ':'
            #ip6 = ip6.rstrip(':')

            # Create certificate
            cert = crypto.X509()
            #cert.set_serial_number(serial)
            cert.set_notBefore(0)
            cert.gmtime_adj_notAfter(self.cert_duration)
            cert.set_issuer(self.ca.get_subject())
            subject = req.get_subject()
            subject.serialNumber = "%u/%u" % (int(prefix, 2), prefix_len)
            cert.set_subject(subject)
            cert.set_pubkey(req.get_pubkey())
            cert.sign(self.key, 'sha1')
            cert = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)

            # Insert certificate into db
            self.db.execute("UPDATE certificates SET email = ?, cert = ? WHERE prefix = ?", (email, cert, prefix) )

        return cert

if __name__ == "__main__":
    main()
