from functools import wraps
import logging, random, socket, time
import miniupnpc


class UPnPException(Exception):
    pass


class Forwarder:
    """
    External port is chosen randomly between 32768 & 49151 included.
    """

    next_refresh = 0
    _next_retry = -1
    _lcg_n = 0

    @classmethod
    def _getExternalPort(cls) -> int:
        # Since _refresh() does not test all ports in a row, we prefer to
        # return random ports to maximize the chance to find a free port.
        # A linear congruential generator should be random enough, without
        # wasting memory/cpu by keeping a full 'shuffle'd list of integers.
        n = cls._lcg_n
        if not n:
            cls._lcg_a = 1 + 4 * random.randrange(0, 2048)
            cls._lcg_c = 1 + 2 * random.randrange(0, 4096)
        n = cls._lcg_n = (n * cls._lcg_a + cls._lcg_c) % 8192
        return 32768 + n

    def __init__(self, description):
        self._description = description
        self._u = miniupnpc.UPnP()
        self._u.discoverdelay = 200
        self._rules = []

    def __getattr__(self, name: str):
        wrapped = getattr(self._u, name)
        def wrapper(*args, **kw):
            try:
                return wrapped(*args, **kw)
            except Exception as e:
                raise UPnPException(str(e))
        return wraps(wrapped)(wrapper)

    def select(self, r, w, t):
        t.append((self.next_refresh, self.refresh))

    def checkExternalIp(self, ip=None):
        if not ip:
            ip = self.refresh()
        try:
            socket.inet_aton(ip)
        except (socket.error, TypeError):
            ip = ()
        return socket.AF_INET, ip and [(ip, str(port or local), proto)
            for local, proto, port in self._rules]

    def addRule(self, local_port, proto):
        self._rules.append([local_port, proto, None])

    def refresh(self):
        if self._next_retry:
            if time.time() < self._next_retry:
                return
            self._next_retry = 0
        else:
            try:
                return self._refresh()
            except UPnPException as e:
                logging.debug("UPnP failure", exc_info=True)
                self.clear()
        try:
            try:
                self.discover()
            except UPnPException as e:
                if str(e) != 'Success':
                    raise
                # WKRD: it likely found no device but let selectigd raise
                #       with a good message
            self.selectigd()
            return self._refresh()
        except UPnPException as e:
            self.next_refresh = self._next_retry = time.time() + 60
            logging.info(e)
            self.clear()

    def _refresh(self):
        t = time.time()
        force = self.next_refresh < t
        if force:
            self.next_refresh = t + 500
            logging.debug('Refreshing port forwarding')
        ip = self.externalipaddress()
        lanaddr = self._u.lanaddr
        # It's too expensive (CPU/network) to try a full range every minute
        # when the router really has no free port. Or with slow routers, it
        # can take more than 15 minutes. So let's use some saner limits:
        t += 1
        retry = 15
        for r in self._rules:
            local, proto, port = r
            if port and not force:
                continue
            desc = '%s (%u/%s)' % (self._description, local, proto)
            args = proto.upper(), lanaddr, local, desc, ''
            while True:
                if port is None:
                    if not retry or t < time.time():
                        raise UPnPException('No free port to redirect %s'
                                            % desc)
                    retry -= 1
                    port = self._getExternalPort()
                try:
                    self.addportmapping(port, *args)
                    break
                except UPnPException as e:
                    if str(e) != 'ConflictInMappingEntry':
                        raise
                    port = None
            if r[2] != port:
                logging.debug('%s forwarded from %s:%u', desc, ip, port)
                r[2] = port
        return ip

    def clear(self):
        for r in self._rules:
            port = r[2]
            if port:
                r[2] = None
                try:
                    self.deleteportmapping(port, r[1].upper())
                except UPnPException:
                    pass
