import argparse, calendar, errno, logging, os, shlex, signal, socket
import struct, subprocess, sys, textwrap, threading, time, traceback

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

def log_exception():
    f = traceback.format_exception(*sys.exc_info())
    logging.error('%s%s', f.pop(), ''.join(f))


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

def networkFromCa(ca):
    return bin(ca.get_serial_number())[3:]

def subnetFromCert(cert):
    return cert.get_subject().CN

def notAfter(cert):
    return calendar.timegm(time.strptime(cert.get_notAfter(),'%Y%m%d%H%M%SZ'))

def dump_address(address):
    return ';'.join(map(','.join, address))

def parse_address(address_list):
    for address in address_list.split(';'):
        try:
            ip, port, proto = address.split(',')
            yield ip, str(port), proto
        except ValueError, e:
            logging.warning("Failed to parse node address %r (%s)",
                            address, e)

def binFromSubnet(subnet):
    p, l = subnet.split('/')
    return bin(int(p))[2:].rjust(int(l), '0')
    
if sys.platform == 'cygwin':
    def _iterRoutes(self):
        # Before Vista
        if platform.system()[10:11] == '5':
            args = ('netsh', 'interface', 'ipv6', 'show', 'route', 'verbose')
        else:
            args = ('ipwin', 'ipv6', 'show', 'route', 'verbose')
        routing_table = subprocess.check_output(args, stderr=subprocess.STDOUT)
        for line in routing_table.splitlines():
            fs = line.split(':', 1)
            test = fs[0].startswith
            if test('Prefix'):
                prefix, prefix_len = fs[1].split('/', 1)
            elif test('Interface'):
                yield (fs[1].strip(),
                        utils.binFromIp(prefix.strip()),
                        int(prefix_len))
else:
    def _iterRoutes():
        with open('/proc/net/ipv6_route') as f:
            routing_table = f.read()
        for line in routing_table.splitlines():
            line = line.split()
            iface = line[-1]
            if 0 < int(line[5], 16) < 1 << 31: # positive metric
                yield (iface, bin(int(line[0], 16))[2:].rjust(128, '0'),
                              int(line[1], 16))

_iterRoutes.__doc__ = """Iterates over all routes

    Amongst all returned routes starting with re6st prefix:
    - one is the local one with our prefix
    - any route with null prefix will be ignored
    - other are reachable routes installed by babeld
    """

def iterRoutes(network, exclude_prefix=None):
    a = len(network)
    for iface, ip, prefix_len in _iterRoutes():
        if ip[:a] == network:
            prefix = ip[a:prefix_len]
            if prefix and prefix != exclude_prefix:
                yield iface, prefix

if 1:
    def _iterRoutes():
        with open('/proc/net/ipv6_route') as f:
            routing_table = f.read()
        for line in routing_table.splitlines():
            line = line.split()
            iface = line[-1]
            if 0 < int(line[5], 16) < 1 << 31: # positive metric
                yield (iface, bin(int(line[0], 16))[2:].rjust(128, '0'),
                              int(line[1], 16))

_iterRoutes.__doc__ = """Iterates over all routes

    Amongst all returned routes starting with re6st prefix:
    - one is the local one with our prefix
    - any route with null prefix will be ignored
    - other are reachable routes installed by babeld
    """

def iterRoutes(network, exclude_prefix=None):
    a = len(network)
    for iface, ip, prefix_len in _iterRoutes():
        if ip[:a] == network:
            prefix = ip[a:prefix_len]
            if prefix and prefix != exclude_prefix:
                yield iface, prefix

def decrypt(key_path, data):
    p = subprocess.Popen(
        ('openssl', 'rsautl', '-decrypt', '-inkey', key_path),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out, err = p.communicate(data)
    if p.returncode:
        raise subprocess.CalledProcessError(p.returncode, 'openssl', err)
    return out

def encrypt(cert, data):
    r, w = os.pipe()
    try:
        threading.Thread(target=os.write, args=(w, cert)).start()
        p = subprocess.Popen(('openssl', 'rsautl', '-encrypt', '-certin',
                              '-inkey', '/proc/self/fd/%u' % r),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        out, err = p.communicate(data)
    finally:
        os.close(r)
        os.close(w)
    if p.returncode:
        raise subprocess.CalledProcessError(p.returncode, 'openssl', err)
    return out

def get_pipename(pipe_id):
    if pipe_id is not None:
        path = '/proc/%u' % os.getpid()
        with open(os.path.join(path, 'winpid'), 'r') as f:
            winpid = f.readline()
        r = os.path.realpath('%s/fd/%s' % (path, pipe_id)).split('/')
        r[2] = winpid.strip()
        return '/'.join(r)
