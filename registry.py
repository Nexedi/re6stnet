#!/usr/bin/env python
import argparse, math, random, select, smtplib, sqlite3, string, struct, socket, time
from email.mime.text import MIMEText
from functools import wraps
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from OpenSSL import crypto
import traceback

IPV6_V6ONLY = 26
SOL_IPV6 = 41

class RequestHandler(SimpleXMLRPCRequestHandler):

    def _dispatch(self, method, params):
        return self.server._dispatch(method, (self,) + params)

class SimpleXMLRPCServer4(SimpleXMLRPCServer):

    allow_reuse_address = True

class SimpleXMLRPCServer6(SimpleXMLRPCServer4):

    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(SOL_IPV6, IPV6_V6ONLY, 1)
        SimpleXMLRPCServer4.server_bind(self)

class main(object):

    def __init__(self):
        self.cert_duration = 365 * 86400

        # Command line parsing
        parser = argparse.ArgumentParser(
                description='Peer discovery http server for vifibnet')
        _ = parser.add_argument
        _('port', type=int, help='Port of the host server')
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
                        proto text not null,
                        date integer default (strftime('%s','now')))""")
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
            if e.args[0] != 'table vifib already exists':
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
        print "Network prefix : %s/%u" % (self.network, len(self.network))

        # Starting server
        server4 = SimpleXMLRPCServer4(('0.0.0.0', self.config.port), requestHandler=RequestHandler, allow_none=True)
        server4.register_instance(self)
        server6 = SimpleXMLRPCServer6(('::', self.config.port), requestHandler=RequestHandler, allow_none=True)
        server6.register_instance(self)
        while True:
            try:
                r, w, e = select.select([server4, server6], [], [])
            except (OSError, select.error) as e:
                if e.args[0] != errno.EINTR:
                    raise
            else:
                for r in r:
                    r._handle_request_noblock()

    def requestToken(self, handler, email):
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

    def requestCertificate(self, handler, token, cert_req):
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

    def getCa(self, handler):
        return crypto.dump_certificate(crypto.FILETYPE_PEM, self.ca)

    def getBootstrapPeer(self, handler):
        # TODO: Insert a flag column for bootstrap ready servers in peers 
        # ( servers which shouldn't go down or change ip and port as opposed to servers owned by particulars )
        # that way, we also ascertain that the server sent is not the new node....
        ip, port, proto = self.db.execute("SELECT ip, port, proto FROM peers ORDER BY random() LIMIT 1").next()
        print "Sending bootstrap peer ( %s, %s, %s)" % (ip, port, proto)
        return ip, port, proto

    def declare(self, handler, address):
        client_address, ip, port, proto = address
        #client_address, _ = handler.client_address
        client_ip1, client_ip2 = struct.unpack('>QQ', socket.inet_pton(socket.AF_INET6, client_address))
        client_ip = bin(client_ip1)[2:].rjust(64, '0') + bin(client_ip2)[2:].rjust(64, '0')
        if client_ip.startswith(self.network):
            prefix = client_ip[len(self.network):]
            prefix, = self.db.execute("SELECT prefix FROM vifib WHERE prefix <= ? ORDER BY prefix DESC LIMIT 1", (prefix,)).next()
            self.db.execute("INSERT OR REPLACE INTO peers VALUES (?,?,?,?)", (prefix, ip, port, proto))
            return True
        else:
            # TODO: use log + DO NOT PRINT BINARY IP
            print "Unauthorized connection from %s which does not start with %s" % (client_ip, self.network)
            return False

    def getPeerList(self, handler, n, address):
        assert 0 < n < 1000
        print "declaring new node"
        if not self.declare(handler, address):
            # TODO: do something intelligent
            raise RuntimeError
        print "sending peers"
        return self.db.execute("SELECT ip, port, proto FROM peers ORDER BY random() LIMIT ?", (n,)).fetchall()

if __name__ == "__main__":
    main()
