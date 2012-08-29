import miniupnpc
import logging
import time


class Forwarder:
    def __init__(self):
        self._u = miniupnpc.UPnP()
        self._u.discoverdelay = 200
        self._rules = []
        self._u.discover()
        self._u.selectigd()
        self._external_ip = self._u.externalipaddress()
        self.next_refresh = time.time()

    def addRule(self, local_port, proto):
        # Init parameters
        external_port = 1023
        desc = 're6stnet openvpn %s server' % proto
        proto = proto.upper()
        lanaddr = self._u.lanaddr
        # Choose a free port
        while True:
            external_port += 1
            if external_port > 65535:
                raise Exception('Failed to redirect %u/%s via UPnP'
                                % (local_port, proto))
            try:
                if not self._u.getspecificportmapping(external_port, proto):
                    args = external_port, proto, lanaddr, local_port, desc, ''
                    self._u.addportmapping(*args)
                    break
            except Exception, e:
                if str(e) != 'ConflictInMappingEntry':
                    raise
        logging.debug('Forwarding %s:%s to %s:%s', self._external_ip,
                      external_port, self._u.lanaddr, local_port)
        self._rules.append(args)
        return self._external_ip, external_port

    def refresh(self):
        logging.debug('Refreshing port forwarding')
        for args in self._rules:
            self._u.addportmapping(*args)
        self.next_refresh = time.time() + 500

    def clear(self):
        for args in self._rules:
            self._u.deleteportmapping(args[0], args[1])
        del self.rules[:]
