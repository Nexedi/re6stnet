import miniupnpc
import time
import utils


class UpnpForward:
    def __init__(self, local_port, protos):
        self._u = miniupnpc.UPnP()
        self._u.discoverdelay = 200
        self.external_port = 1000
        self._local_port = local_port
        self._protos = protos

        self._u.discover()
        self._u.selectigd()

        if 'udp' in protos:
            while self._u.getspecificportmapping(self.external_port,
                    'UDP') != None:
                self.external_port += 1
                if self.external_port == 65536:
                    raise Exception
        if 'tcp-server' in protos:
            while self._u.getspecificportmapping(self.external_port,
                    'TCP') != None:
                self.external_port += 1
                if self._external_port == 65536:
                    raise Exception

        if 'udp' in protos:
            self._u.addportmapping(self.external_port, 'UDP',
                    self._u.lanaddr, local_port, 'Vifib openvpn server', '')
        if 'tcp-server' in protos:
            self._u.addportmapping(self.external_port, 'TCP',
                    self._u.lanaddr, local_port, 'Vifib openvpn server', '')

        self.external_ip = self._u.externalipaddress()
        utils.log('Forwarding %s:%s to %s:%s' % (self.external_ip,
                self.external_port, self._u.lanaddr, local_port), 3)
        self.next_refresh = time.time() + 3600

    def Refresh(self):
        if 'udp' in self._protos:
            self._u.addportmapping(self.external_port, 'UDP', self._u.lanaddr,
                    self._local_port, 'Vifib openvpn server', '')
        if 'tcp-server' in self._protos:
            self._u.addportmapping(self.external_port, 'TCP', self._u.lanaddr,
                    self._local_port, 'Vifib openvpn server', '')
        self.next_refresh = time.time() + 3600
