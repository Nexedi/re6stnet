import argparse, errno, hashlib, logging, os, select as _select
import shlex, signal, socket, sqlite3, struct, subprocess
import sys, textwrap, threading, time, traceback

HMAC_LEN = len(hashlib.sha1('').digest())

class ReexecException(Exception):
    pass

try:
    subprocess.CalledProcessError(0, '', '')
except TypeError: # BBB: Python < 2.7
    def __init__(self, returncode, cmd, output=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
    subprocess.CalledProcessError.__init__ = __init__

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


class exit(object):

    status = None

    def __init__(self):
        l = threading.Lock()
        self.acquire = l.acquire
        r = l.release
        def release():
            try:
                if self.status is not None:
                    self.release = r
                    sys.exit(self.status)
            finally:
                r()
        self.release = release

    def __enter__(self):
        self.acquire()

    def __exit__(self, t, v, tb):
        self.release()

    def kill_main(self, status):
        self.status = status
        os.kill(os.getpid(), signal.SIGTERM)

    def signal(self, status, *sigs):
        def handler(*args):
            if self.status is None:
                self.status = status
            if self.acquire(0):
                self.release()
        for sig in sigs:
            signal.signal(sig, handler)

exit = exit()


class Popen(subprocess.Popen):

    def __init__(self, *args, **kw):
        try:
            super(Popen, self).__init__(*args, **kw)
        except OSError, e:
            if e.errno != errno.ENOMEM:
                raise
            self.returncode = -1

    def stop(self):
        if self.pid and self.returncode is None:
            self.terminate()
            t = threading.Timer(5, self.kill)
            t.start()
            # PY3: use waitid(WNOWAIT) and call self.poll() after t.cancel()
            r = self.wait()
            t.cancel()
            return r


def select(R, W, T):
    try:
        r, w, _ = _select.select(R, W, (),
            max(0, min(T)[0] - time.time()) if T else None)
    except _select.error as e:
        if e.args[0] != errno.EINTR:
            raise
        return
    for r in r:
        R[r]()
    for w in w:
        W[w]()
    t = time.time()
    for next_refresh, refresh in T:
        if next_refresh <= t:
            refresh()

def makedirs(*args):
    try:
        os.makedirs(*args)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

def binFromIp(ip):
    return binFromRawIp(socket.inet_pton(socket.AF_INET6, ip))

def binFromRawIp(ip):
    ip1, ip2 = struct.unpack('>QQ', ip)
    return bin(ip1)[2:].rjust(64, '0') + bin(ip2)[2:].rjust(64, '0')


def ipFromBin(ip, suffix=''):
    suffix_len = 128 - len(ip)
    if suffix_len > 0:
        ip += suffix.rjust(suffix_len, '0')
    elif suffix_len:
        sys.exit("Prefix exceeds 128 bits")
    return socket.inet_ntop(socket.AF_INET6,
        struct.pack('>QQ', int(ip[:64], 2), int(ip[64:], 2)))

def dump_address(address):
    return ';'.join(map(','.join, address))

def parse_address(address_list):
    for address in address_list.split(';'):
        try:
            a = ip, port, proto = address.split(',')
            int(port)
            yield a
        except ValueError, e:
            logging.warning("Failed to parse node address %r (%s)",
                            address, e)

def binFromSubnet(subnet):
    p, l = subnet.split('/')
    return bin(int(p))[2:].rjust(int(l), '0')

def newHmacSecret():
    from random import getrandbits as g
    pack = struct.Struct(">QQI").pack
    assert len(pack(0,0,0)) == HMAC_LEN
    return lambda x=None: pack(g(64) if x is None else x, g(64), g(32))
newHmacSecret = newHmacSecret()

def sqliteCreateTable(db, name, *columns):
    sql = "CREATE TABLE %s (%s)" % (name, ','.join('\n  ' + x for x in columns))
    for x, in db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' and name=?""",
            (name,)):
        if x == sql:
            return
        raise sqlite3.OperationalError(
            "table %r already exists with unexpected schema" % name)
    db.execute(sql)
    return True
