import argparse, errno, fcntl, hashlib, logging, os, select as _select
import shlex, signal, socket, sqlite3, struct, subprocess
import sys, textwrap, threading, time, traceback
from collections.abc import Iterator, Mapping

HMAC_LEN = len(hashlib.sha1(b'').digest())

class ReexecException(Exception):
    pass

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
        if self._reopen and self.lock.acquire(False):
            self.release()

    def async_reopen(self, *_):
        self._reopen = True
        if self.lock.acquire(False):
            self.release()

def setupLog(log_level: int, filename: str | None=None, **kw):
    if log_level and filename:
        makedirs(os.path.dirname(filename))
        handler = FileHandler(filename)
        sig = handler.async_reopen
    else:
        handler = logging.StreamHandler()
        sig = signal.SIG_IGN
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)-9s %(message)s', '%Y-%m-%d %H:%M:%S'))
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
        return super()._get_help_string(action) \
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
        super().__init__(formatter_class=self._HelpFormatter,
            epilog="""Options can be read from a file. For example:
  $ cat OPTIONS_FILE
  ca /etc/re6stnet/ca.crt""", **kw)


class exit:

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
            if self.acquire(False):
                self.release()
        for sig in sigs:
            signal.signal(sig, handler)

exit = exit()


class Popen(subprocess.Popen):

    def __init__(self, *args, **kw):
        self._args = tuple(args[0] if args else kw['args'])
        try:
            super().__init__(*args, **kw)
        except OSError as e:
            if e.errno != errno.ENOMEM:
                raise
            self.returncode = -1

    def send_signal(self, sig):
        logging.info('Sending signal %s to pid %s %r',
                     sig, self.pid, self._args)
        # We don't need the change from https://bugs.python.org/issue38630
        # and it would complicate stop()
        assert self.returncode is None
        os.kill(self.pid, sig)

    def stop(self):
        if self.pid and self.returncode is None:
            self.terminate()
            t = threading.Timer(5, self.kill)
            t.start()
            os.waitid(os.P_PID, self.pid, os.WEXITED | os.WNOWAIT)
            t.cancel()
            self.poll()


def setCloexec(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)

def select(R: Mapping, W: Mapping, T):
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
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

def binFromIp(ip: str) -> str:
    return binFromRawIp(socket.inet_pton(socket.AF_INET6, ip))

def binFromRawIp(ip: bytes) -> str:
    ip1, ip2 = struct.unpack('>QQ', ip)
    return bin(ip1)[2:].rjust(64, '0') + bin(ip2)[2:].rjust(64, '0')


def ipFromBin(ip: str, suffix='') -> str:
    suffix_len = 128 - len(ip)
    if suffix_len > 0:
        ip += suffix.rjust(suffix_len, '0')
    elif suffix_len:
        sys.exit("Prefix exceeds 128 bits")
    return socket.inet_ntop(socket.AF_INET6,
        struct.pack('>QQ', int(ip[:64], 2), int(ip[64:], 2)))

def dump_address(address: str) -> str:
    return ';'.join(map(','.join, address))

# Yield ip, port, protocol, and country if it is in the address
def parse_address(address_list: str) -> Iterator[tuple[str, str, str, str]]:
    for address in address_list.split(';'):
        try:
            a = address.split(',')
            int(a[1]) # Check if port is an int
            yield tuple(a[:4])
        except ValueError as e:
            logging.warning("Failed to parse node address %r (%s)",
                            address, e)

def binFromSubnet(subnet: str) -> str:
    p, l = subnet.split('/')
    return bin(int(p))[2:].rjust(int(l), '0')

def _newHmacSecret():
    from random import getrandbits as g
    pack = struct.Struct(">QQI").pack
    assert len(pack(0,0,0)) == HMAC_LEN
    # A closure is built to avoid rebuilding the `pack` function at each call.
    return lambda x=None: pack(g(64) if x is None else x, g(64), g(32))

newHmacSecret = _newHmacSecret() # https://github.com/python/mypy/issues/1174

### Integer serialization
# - supports values from 0 to 0x202020202020201f
# - preserves ordering
# - there's always a unique way to encode a value
# - the 3 first bits code the number of bytes

def packInteger(i: int) -> bytes:
    for n in range(8):
        x = 32 << 8 * n
        if i < x:
            return struct.pack("!Q", i + n * x)[7-n:]
        i -= x
    raise OverflowError

def unpackInteger(x: bytes) -> tuple[int, int] | None:
    n = x[0] >> 5
    try:
        i, = struct.unpack("!Q", b'\0' * (7 - n) + x[:n+1])
    except struct.error:
        return
    return sum((32 << 8 * i for i in range(n)),
                i - (n * 32 << 8 * n)), n + 1

###

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
