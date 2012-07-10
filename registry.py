#!/usr/bin/env python
import argparse, math, random, smtplib, sqlite3, string, time
from email.mime.text import MIMEText
from SimpleXMLRPCServer import SimpleXMLRPCServer
from OpenSSL import crypto
import netaddr
import traceback

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
        _('--mailhost', required=True,
                help='SMTP server mail host')
        self.config = parser.parse_args()

        # Database initializing
        self.db = sqlite3.connect(self.config.db, isolation_level=None)
        self.db.execute("""CREATE TABLE IF NOT EXISTS peers (
                        prefix text primary key not null,
                        ip text not null,
                        port integer not null,
                        proto text not null)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS tokens (
                        token text primary key not null,
                        email text not null,
                        prefix_len integer not null,
                        date integer not null)""")
        try:
            self.db.execute("""CREATE TABLE vifib (
                               prefix text primary key not null,
                               email text,
                               cert text)""")
        except sqlite3.OperationalError, e:
            if e.args[0] == 'table vifib already exists':
                pass
            else:
                raise RuntimeError
        else:
            self.db.execute("INSERT INTO vifib VALUES ('',null,null)")


        # Loading certificates
        with open(self.config.ca) as f:
            self.ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        with open(self.config.key) as f:
            self.key = crypto.load_privatekey(crypto.FILETYPE_PEM, f.read())
        # Get vifib network prefix
        self.network = bin(self.ca.get_serial_number())[3:]

        # Starting server
        server = SimpleXMLRPCServer(("localhost", 8000), allow_none=True)
        server.register_instance(self)
        server.serve_forever()

    def requestToken(self, email):
        while True:
            # Generating token
            token = ''.join(random.sample(string.ascii_lowercase, 8))
            # Updating database
            try:
                self.db.execute("INSERT INTO tokens VALUES (?,?,?,?)", (token, email, 16, int(time.time())))
                break
            except sqlite3.IntegrityError, e:
                pass

        # Creating and sending email
        s = smtplib.SMTP(self.config.mailhost)
        me = 'postmaster@vifibnet.com'
        msg = MIMEText('Hello world !\nYour token : %s' % (token,))
        msg['Subject'] = '[Vifibnet] Token Request'
        msg['From'] = me
        msg['To'] = email
        s.sendmail(me, email, msg.as_string())
        s.quit()

    def _getPrefix(self, prefix_len):
        assert 0 < prefix_len <= 128 - len(self.network)
        for prefix, in self.db.execute("""SELECT prefix FROM vifib WHERE length(prefix) <= ? AND cert is null
                                         ORDER BY length(prefix) DESC""", (prefix_len,)):
            while len(prefix) < prefix_len:
                self.db.execute("UPDATE vifib SET prefix = ? WHERE prefix = ?", (prefix + '1', prefix))
                prefix += '0'
                self.db.execute("INSERT INTO vifib VALUES (?,null,null)", (prefix,))
            return prefix
        raise RuntimeError # TODO: raise better exception

    def requestCertificate(self, token, cert_req):
      try:
        req = crypto.load_certificate_request(crypto.FILETYPE_PEM, cert_req)
        with self.db:
            try:
                token, email, prefix_len, _ = self.db.execute("SELECT * FROM tokens WHERE token = ?", (token,)).next()
            except StopIteration:
                # TODO: return nice error message
                raise
            self.db.execute("DELETE FROM tokens WHERE token = ?", (token,))

            # Get a new prefix
            prefix = self._getPrefix(prefix_len)

            # Create certificate
            cert = crypto.X509()
            #cert.set_serial_number(serial)
            cert.gmtime_adj_notBefore(0)
            cert.gmtime_adj_notAfter(self.cert_duration)
            cert.set_issuer(self.ca.get_subject())
            subject = req.get_subject()
            subject.serialNumber = "%u/%u" % (int(prefix, 2), prefix_len)
            cert.set_subject(subject)
            cert.set_pubkey(req.get_pubkey())
            cert.sign(self.key, 'sha1')
            cert = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)

            # Insert certificate into db
            self.db.execute("UPDATE vifib SET email = ?, cert = ? WHERE prefix = ?", (email, cert, prefix) )

        return cert
      except:
        traceback.print_exc()
        raise

    def getCa(self):
        return crypto.dump_certificate(crypto.FILETYPE_PEM, self.ca)

    def getPeerList(self, n):
        assert 0 < n < 1000
        return self.db.execute("SELECT ip, port, proto FROM peers ORDER BY random() LIMIT ?", (n,)).fetchall()


if __name__ == "__main__":
    main()
