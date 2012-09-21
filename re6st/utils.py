import argparse, errno, logging, os, shlex, signal, socket
import struct, subprocess, textwrap, threading, time
from OpenSSL import crypto

logging_levels = logging.WARNING, logging.INFO, logging.DEBUG, 5

class FileHandler(logging.FileHandler):

    _reopen = False

    def release(self):
        try:
            if self._reopen:
                self._reopen = False
                self.close()
                self._open()
        finally:
            self.lock.release()
        # In the rare case _reopen is set just before the lock was released
        if self._reopen and self.lock.acquire(0):
            self.release()

    def async_reopen(self, *_):
        self._reopen = True
        if self.lock.acquire(0):
            self.release()

def setupLog(log_level, filename=None, **kw):
    if log_level and filename:
        makedirs(os.path.dirname(filename))
        handler = FileHandler(filename)
        sig = handler.async_reopen
    else:
        handler = logging.StreamHandler()
        sig = signal.SIG_IGN
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)-9s %(message)s', '%d-%m-%Y %H:%M:%S'))
    root = logging.getLogger()
    root.addHandler(handler)
    signal.signal(signal.SIGUSR1, sig)
    if log_level:
        root.setLevel(logging_levels[log_level-1])
    else:
        logging.disable(logging.CRITICAL)
    logging.addLevelName(5, 'TRACE')
    logging.trace = lambda *args, **kw: logging.log(5, *args, **kw)


class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter):

    def _get_help_string(self, action):
        return super(HelpFormatter, self)._get_help_string(action) \
            if action.default else action.help

    def _split_lines(self, text, width):
        """Preserves new lines in option descriptions"""
        lines = []
        for text in text.splitlines():
            lines += textwrap.wrap(text, width)
        return lines

    def _fill_text(self, text, width, indent):
        """Preserves new lines in other descriptions"""
        kw = dict(width=width, initial_indent=indent, subsequent_indent=indent)
        return '\n'.join(textwrap.fill(t, **kw) for t in text.splitlines())

class ArgParser(argparse.ArgumentParser):

    class _HelpFormatter(HelpFormatter):

        def _format_actions_usage(self, actions, groups):
            r = HelpFormatter._format_actions_usage(self, actions, groups)
            if actions and actions[0].option_strings:
                r = '[@OPTIONS_FILE] ' + r
            return r

    _ca_help = "Certificate authority (CA) file in .pem format." \
               " Serial number defines the prefix of the network."

    def convert_arg_line_to_args(self, arg_line):
        if arg_line.split('#', 1)[0].rstrip():
            if arg_line.startswith('@'):
                yield arg_line
                return
            arg_line = shlex.split(arg_line)
            arg = '--' + arg_line.pop(0)
            yield arg[arg not in self._option_string_actions:]
            for arg in arg_line:
                yield arg

    def __init__(self, **kw):
        super(ArgParser, self).__init__(formatter_class=self._HelpFormatter,
            epilog="""Options can be read from a file. For example:
  $ cat OPTIONS_FILE
  ca /etc/re6stnet/ca.crt""", **kw)


class Popen(subprocess.Popen):

    def stop(self):
        self.terminate()
        t = threading.Timer(5, self.kill)
        t.start()
        r = self.wait()
        t.cancel()
        return r


def makedirs(path):
    try:
        os.makedirs(path)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

def binFromIp(ip):
    ip1, ip2 = struct.unpack('>QQ', socket.inet_pton(socket.AF_INET6, ip))
    return bin(ip1)[2:].rjust(64, '0') + bin(ip2)[2:].rjust(64, '0')


def ipFromBin(ip, suffix=''):
    suffix_len = 128 - len(ip)
    if suffix_len > 0:
        ip += suffix.rjust(suffix_len, '0')
    elif suffix_len:
        sys.exit("Prefix exceeds 128 bits")
    return socket.inet_ntop(socket.AF_INET6,
        struct.pack('>QQ', int(ip[:64], 2), int(ip[64:], 2)))

def networkFromCa(ca_path):
    # Get network prefix from ca.crt
    with open(ca_path, 'r') as f:
        ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        return bin(ca.get_serial_number())[3:]

def subnetFromCert(cert_path):
    # Get ip from cert.crt
    with open(cert_path, 'r') as f:
        cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        return cert.get_subject().CN

def address_str(address):
    return ';'.join(map(','.join, address))


def address_list(address_list):
    return list(tuple(address.split(','))
        for address in address_list.split(';'))


def binFromSubnet(subnet):
    p, l = subnet.split('/')
    return bin(int(p))[2:].rjust(int(l), '0')
