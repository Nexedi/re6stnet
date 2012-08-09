import miniupnpc
import logging
import time


class NoUPnPDevice(Exception):
    def __init__(self):
        pass

    def __str__(self):
        return 'No upnp device found'


class Forwarder:
    def __init__(self):
        self._u = miniupnpc.UPnP()
        self._u.discoverdelay = 200
        self._rules = []
        self._u.discover()
        try:
            self._u.selectigd()
        except:
            raise NoUPnPDevice
        self._external_ip = self._u.externalipaddress()
        self.next_refresh = time.time()

    def  AddRule(self, local_port, proto):
        # Init parameters
        external_port = 1000
        if proto == 'udp':
            upnp_proto = 'UDP'
        elif proto == 'tcp-server':
            upnp_proto = 'TCP'
        else:
            logging.info('Unknown protocol : %s' % proto)
            raise RuntimeError

        # Choose a free port
        while True:
            while self._u.getspecificportmapping(external_port,
                    upnp_proto) != None:
                external_port += 1
                if external_port == 65536:
                    return None

            # Make the redirection
            if self._u.addportmapping(external_port, upnp_proto, self._u.lanaddr,
                    int(local_port), 're6stnet openvpn server', ''):
                logging.debug('Forwarding %s:%s to %s:%s' % (self._external_ip,
                        external_port, self._u.lanaddr, local_port))
                self._rules.append((external_port, int(local_port), upnp_proto))
                return (self._external_ip, str(external_port), proto)

    def refresh(self):
        logging.debug('Refreshing port forwarding')
        for external_port, local_port, proto in self._rules:
            self._u.addportmapping(external_port, proto, self._u.lanaddr,
                    local_port, 're6stnet openvpn server', '')
        self.next_refresh = time.time() + 3600
