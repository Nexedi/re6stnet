#!/usr/bin/env python
import argparse, random, smtplib, sqlite3
from email.mime.text import MIMEText
from SimpleXMLRPCServer import SimpleXMLRPCServer
from OpenSSL import crypto
import netaddr

class main(object):

    def __init__(self):
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
        _('--network', required=True,
                help='Vifib subnet')
        config = parser.parser_arg()

        # Database initializing
        self.db = sqlite3.connect(config.db, isolation_level=None)
        self.db.execute("""CREATE TABLE IF NOT EXISTS tokens (
                        token text primary key not null,
                        email text not null,
                        prefix_len integer not null default 16,
                        date integer not null)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS certificates (
                        prefix text primary key not null,
                        email text not null,
                        cert text not null)""")

        # Loading certificates
        with open(config.ca) as f:
            self.ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        with open(config.key) as f:
            self.key = crypto.load_privatekey(crypto.FILETYPE_PEM, f.read())

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

    def requestCertificate(self, token, cert_req):
        n = len(cert_req_list)
        req = crypto.load_certificate_request(crypto.FILETYPE_PEM, cert_req)
        try:
            # TODO : check syntax
            token, email, prefix_len, _ = self.db.execute("SELECT * FROM tokens WHERE token = ?", (token,)).fetchone()
            self.db.execute("DELETE FROM tokens WHERE token = ?", (token,))

            # Create a new prefix
            # TODO : FIX !
            # i impair => ok
            # récursif sinon
            for i, prefix in enumerate(self.db.execute("""SELECT DISTINCT substr(prefix,1,?) FROM certificates 
                                        WHERE length(prefix) >= ? ORDER BY prefix""", (prefix_len, prefix_len))):
                if i != int(prefix, 2):
                    pass
                    break
            else:
                 prefix = i

            # create certificate
            cert = crypto.X509()
            #cert.set_serial_number(serial)
            #cert.gmtime_adj_notBefore(notBefore)
            #cert.gmtime_adj_notAfter(notAfter)
            cert.set_issuer(self.ca.get_subject())
            cert.set_subject(req.get_subject())
            cert.set_pubkey(req.get_pubkey())
            cert.sign(self.key, 'sha1')
            cert = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)

            # Insert certificate into db
            self.db.execute("INSERT INTO certificates (?,?)", (, email, cert) )

            # Returning certificate
            return cert
        except: Exception:
            # TODO : what to do ?
            pass

if __name__ == "__main__":
    main()
