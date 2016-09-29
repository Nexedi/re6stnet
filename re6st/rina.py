import errno, glob, logging, os, select
import socket, struct, threading, time, weakref
from . import utils

# Experimental support for RINA (Recursive InterNetwork Architecture).
#   https://github.com/IRATI/stack (revision b7a7552 or later)
# This relies on pull requests #996 and #997.

DEFAULT_DIF = "default.dif"
IPCM_PROMPT = "IPCM >>> "
IPCM_SOCK = '/run/ipcm-console.sock'
IPCP_NAME = 're6st'
NORMAL_DIF = "normal.DIF"
PORT = 3359

resolve_thread = None
shim = None

def ap_name(prefix):
    # : and - are already used to separate the name from the instance number.
    # Also not using / because the IPCP log path is named after the IPCP name.
    return "%s.%s.%s" % (IPCP_NAME, int(prefix, 2), len(prefix))

def ap_prefix(name):
    a, b, c = name.split('.')
    if a == IPCP_NAME:
        return utils.binFromSubnet(b + '/' + c)

@apply
class ipcm(object):

    def __call__(self, *args):
        try:
            try:
                s = self._socket
            except AttributeError:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(IPCM_SOCK)
                if s.recv(len(IPCM_PROMPT) + 1) != IPCM_PROMPT:
                    return
                self._socket = s
            x = ' '.join(map(str, args))
            logging.debug("%s%s", IPCM_PROMPT, x)
            s.send(x + '\n')
            r = []
            last = ''
            while 1:
                d = s.recv(4096)
                if not d:
                    break
                r += (last + d).split('\n')
                last = r.pop()
                if last == IPCM_PROMPT:
                    for x in r:
                        logging.debug("%s", x)
                    return r
        except socket.error, e:
            logging.info("RINA: %s", e)
        del self._socket

    def iterIpcp(self):
        i = iter(self("list-ipcps") or ())
        for line in i:
            if line.startswith("Current IPC processes"):
                l = lambda x: () if x == '-' else map(str.strip, x.split(','))
                for line in i:
                    if not line:
                        return
                    id, name, type, state, reg_apps, ports = map(
                        str.strip, line.split('|'))
                    yield (int(id), name.replace(':', '-'), type, state,
                           l(reg_apps), map(int, l(ports)))

    def queryRib(self, *args):
        r = self("query-rib", *args)
        if r:
            i = iter(r)
            for r in i:
                if r:
                    name, class_, instance = r.split('; ')
                    assert name.startswith('Name: '), name
                    assert class_.startswith('Class: '), class_
                    assert instance.startswith('Instance: '), instance
                    r = next(i)
                    assert r.startswith('Value: '), r
                    value = [r[7:]]
                    while True:
                        r = next(i)
                        if not r:
                            break
                        value.append(r)
                    value = '\n'.join(value)
                    yield (name[6:], class_[7:], instance[10:],
                           None if value == '-' else value)

    def iterNeigh(self, ipcp_id):
        for x in self.queryRib(ipcp_id, "Neighbor",
                               "/difManagement/enrollment/neighbors/"):
            x = dict(map(str.strip, x.split(':')) for x in x[3].split(';'))
            yield (x['Name'],
                int(x['Address']),
                int(x['Enrolled']),
                x['Supporting DIF Name'],
                int(x['Underlying port-id']),
                int(x['Number of enroll. attempts']))

class Shim(object):

    normal_id = None

    def __init__(self, ipcp_id, dif):
        self.ipcp_id = ipcp_id
        self.dif = dif
        self._asking_info = {}
        self._enabled = weakref.WeakValueDictionary()

    def _kernel(self, **kw):
        fd = os.open("/sys/rina/ipcps/%s/config" % self.ipcp_id, os.O_WRONLY)
        try:
            os.write(fd, ''.join("%s\0%s\0" % x for x in kw.iteritems()))
        finally:
            os.close(fd)

    def _enroll(self, tm, prefix):
        # This condition is only optimization, since the kernel may already
        # have an entry for this neighbour.
        if prefix not in self._enabled:
            ap = ap_name(prefix)
            ip = utils.ipFromBin(tm._network + prefix, '1')
            port = str(PORT)
            self._kernel(dirEntry="1:%s:%s0:%s:%s%s:%s" % (
                len(ap), ap, len(ip), ip, len(port), port))
        self._enabled[prefix] = tm._getPeer(prefix)

    def init(self, tm):
        global resolve_thread
        if resolve_thread is None:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.bind("\0rina.resolve_ipcp_address")
            s.listen(5)
            resolve_thread = threading.Thread(target=self._resolve, args=(s,))
            resolve_thread.daemon = True
            resolve_thread.start()
        prefix = tm._prefix
        self._enabled[prefix] = tm.cert
        self._asking_info[prefix] = float('inf')

    def update(self, tm):
        enabled = self._enabled
        ap = ap_name(tm._prefix)
        name = ap + "-1--"
        step = 0 # do never retry immediately
        while 1:
            normal_id = None
            for ipcp in ipcm.iterIpcp():
                if ipcp[0] == self.ipcp_id:
                    registered = ipcp[4]
                elif ipcp[1] == name:
                    normal_id = ipcp[0]
                    normal_status = ipcp[3]
                elif ipcp[1] in registered:
                    if step or not ipcm("destroy-ipcp", ipcp[0]):
                        return
                    step = 1
            if name in registered:
                break
            if normal_id is None:
                if step > 1 or not ipcm("create-ipcp", ap, 1, "normal-ipc"):
                    return
                step = 2
            elif normal_status == "INITIALIZED":
                if step > 2 or not ipcm("assign-to-dif", normal_id,
                                        NORMAL_DIF, DEFAULT_DIF):
                    return
                step = 3
            elif normal_status.startswith("ASSIGNED TO DIF"):
                enabled.clear()
                self.init(tm)
                port = str(PORT)
                self._kernel(
                    hostname=utils.ipFromBin(tm._network + tm._prefix, '1'),
                    expReg="1:%s:%s0:%s:%s" % (len(ap), ap, len(port), port))
                if step > 3 or not ipcm("register-at-dif", normal_id, self.dif):
                    return
                step = 4
            else:
                return
        asking_info = self._asking_info
        enrolled = set(ap_prefix(neigh[0].split('-', 1)[0])
            for neigh in ipcm.iterNeigh(normal_id))
        now = time.time()
        for neigh_routes in tm.ctl.neighbours.itervalues():
            for prefix in neigh_routes[1]:
                if not prefix or prefix in enrolled:
                    continue
                if prefix in enabled:
                    # Avoid enrollment to a neighbour
                    # that does not know our address.
                    if prefix not in asking_info:
                        r = ipcm("enroll-to-dif", normal_id,
                                 NORMAL_DIF, self.dif, ap_name(prefix), 1)
                        if r and 'failed' in r[0]:
                            del enabled[prefix]
                        # Enrolling may take a while
                        # so don't block for too long.
                        if now + 1 < time.time():
                            return
                        continue
                if asking_info.get(prefix, 0) < now and tm.askInfo(prefix):
                    self._enroll(tm, prefix)
                    asking_info[prefix] = now + 60

    def enabled(self, tm, prefix, enroll):
        logging.debug("RINA: enabled(%s, %s)", prefix, enroll)
        if enroll:
            self._asking_info.pop(prefix, None)
            self._enroll(tm, prefix)
        else:
            self._asking_info[prefix] = float('inf')
            self._enabled.pop(prefix, None)

    @staticmethod
    def _resolve(sock):
        clients = []
        try:
            while True:
                try:
                    s = select.select([sock] + clients, (), ())
                except select.error as e:
                    if e.args[0] != errno.EINTR:
                        raise
                    continue
                for s in s[0]:
                    if s is sock:
                        clients.append(s.accept()[0])
                        continue
                    try:
                        d = s.recv(4096)
                        if d:
                            try:
                                address = 0
                                dif, name, instance = d.split('\n')
                                if dif == NORMAL_DIF and instance == "1":
                                    prefix = ap_prefix(name)
                                    if prefix:
                                        try:
                                            address = 1 + (
                                                shim._enabled[prefix]
                                                    .subject_serial)
                                        except KeyError:
                                            pass
                            except:
                                logging.info("RINA: resolve(%r)", d)
                                raise
                            logging.debug("RINA: resolve(%r) -> %r", d, address)
                            s.send(struct.pack('=I', address))
                            continue
                    except Exception, e:
                        logging.info("RINA: %s", e)
                    clients.remove(s)
                    s.close()
        finally:
            global resolve_thread
            resolve_thread = None
            sock.close()
            for s in clients:
                s.close()

def sysfs_read(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        return os.read(fd, 4096).strip()
    finally:
        os.close(fd)

update = dummy_update = lambda tunnel_manager, route_dumped: False
if os.path.isdir("/sys/rina"):
    def update(tunnel_manager, route_dumped):
        global shim, update
        try:
            for ipcp in glob.glob("/sys/rina/ipcps/*"):
                if sysfs_read(ipcp + "/type") != "shim-tcp-udp" or \
                  sysfs_read(ipcp + "/name") != IPCP_NAME + "/1//":
                    continue
                if not os.access(ipcp + "/config", os.W_OK):
                    logging.exception("RINA: This kernel does not support"
                        " dynamic updates of shim-tcp-udp configuration.")
                    update = dummy_update
                    return False
                dif = sysfs_read(ipcp + "/dif")
                if dif.endswith("///"):
                    if shim is None:
                        shim = Shim(int(ipcp.rsplit("/", 1)[1]), dif[:-3])
                        shim.init(tunnel_manager)
                    if route_dumped:
                        shim.update(tunnel_manager)
                    return True
            shim = None
        except Exception, e:
            logging.info("RINA: %s", e)
        return False

def enabled(*args):
    if shim:
        try:
            shim.enabled(*args)
        except Exception, e:
            logging.info("RINA: %s", e)
