import os, struct, subprocess, yaml
from socket import socket, AF_NETLINK, NETLINK_ROUTE, SOCK_RAW
from . import utils

RTMGRP_IPV6_IFINFO = 0x800
RTM_NEWLINK = 16
IFLA_IFNAME = 3

def addInterface(ifname):
    subprocess.call(['pim-dm', '-6', '-aisr', ifname])
    subprocess.call(['pim-dm', '-aimld', ifname])

def removeInterface(ifname):
    subprocess.call(['pim-dm', '-6', '-ri', ifname])
    subprocess.call(['pim-dm', '-6', '-rimld', ifname])


class unpacker(object):
    def __init__(self, buf):
        self._buf = buf
        self._offset = 0
    def __call__(self, fmt):
        result = struct.unpack_from(fmt, self._buf, self._offset)
        self._offset += struct.calcsize(fmt)
        return result


class PimDm(object):
    def __init__(self):
        self.not_ready_iface_list = []

        s_netlink = socket(AF_NETLINK, SOCK_RAW, NETLINK_ROUTE)
        s_netlink.setblocking(False)
        s_netlink.bind((os.getpid(), RTMGRP_IPV6_IFINFO))
        self.s_netlink = s_netlink

    def addPimInterfaceWhenReady(self):
        if not self.not_ready_iface_list:
            return

        data = self.s_netlink.recv(65535)
        unpack = unpacker(data)
        msg_len, msg_type, flags, seq, pid = unpack("=LHHLL")
        if msg_type != RTM_NEWLINK:
            return

        family, _, if_type, index, flags, change = unpack("=BBHiII")

        while msg_len - unpack._offset:
            rta_len, rta_type = unpack("=HH")
            if rta_len < 4:
                break
            rta_data = unpack("%ds" % rta_len)[0].rstrip('\00\n' + chr(1))

            if rta_type == IFLA_IFNAME:
                if rta_data in self.not_ready_iface_list:
                    addInterface(rta_data)
                    self.not_ready_iface_list.remove(rta_data)
                break

            unpack._offset += (rta_len - 1) & ~(4 - 1)

    def isInterfaceUp(self, ifname):
        with open(os.path.join('/sys/class/net', ifname, 'operstate')) as state_file:
            return 'up' in state_file.read()

    def run(self, iface_list, run_path):
        # pim-dm requires interface to be up at startup, 
        # but can handle interfaces going down then up again
        for iface in iface_list[:]:
            if not self.isInterfaceUp(iface):
                self.not_ready_iface_list.append(iface)
                iface_list.remove(iface)

        enabled = (('enabled', True), ('state_refresh', True))
        conf = {
            'PIM-DM': {
                'Interfaces': dict.fromkeys(iface_list, {'ipv6': dict(enabled)}),
            },
            'MLD': {
                'Interfaces': dict.fromkeys(iface_list, dict((enabled[0],))),
            },
        }

        conf_file_path = os.path.join(run_path, 'pim-dm.conf')
        with open(conf_file_path, 'w') as conf_file:
            yaml.dump(conf, conf_file)

        return utils.Popen(['pim-dm', '-config', conf_file_path])
