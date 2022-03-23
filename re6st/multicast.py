import  os, struct, subprocess, yaml
from ctypes import (
    Structure, Union, POINTER,
    pointer, get_errno,
    c_ushort, c_byte, c_void_p, c_char_p, c_uint, c_int,
)
import ctypes.util
from socket import socket, AF_INET6, AF_NETLINK, NETLINK_ROUTE, SOCK_RAW
from . import utils

RTMGRP_IPV6_IFINFO = 0x800
RTM_NEWLINK = 16
IFLA_IFNAME = 3

class struct_sockaddr(Structure):
    _fields_ = [
        ('sa_family', c_ushort),
        ('sa_data', c_byte * 14),
    ]

class union_ifa_ifu(Union):
    _fields_ = [
        ('ifu_broadaddr', POINTER(struct_sockaddr)),
        ('ifu_dstaddr', POINTER(struct_sockaddr)),
    ]

class struct_ifaddrs(Structure):
    pass
struct_ifaddrs._fields_ = [
    ('ifa_next', POINTER(struct_ifaddrs)),
    ('ifa_name', c_char_p),
    ('ifa_flags', c_uint),
    ('ifa_addr', POINTER(struct_sockaddr)),
    ('ifa_netmask', POINTER(struct_sockaddr)),
    ('ifa_ifu', union_ifa_ifu),
    ('ifa_data', c_void_p),
]

libc = ctypes.CDLL(ctypes.util.find_library('c'))
_getifaddrs = libc.getifaddrs
_getifaddrs.restype = c_int
_getifaddrs.argtypes = [POINTER(POINTER(struct_ifaddrs))]
_freeifaddrs = libc.freeifaddrs
_freeifaddrs.restype = None
_freeifaddrs.argtypes = [POINTER(struct_ifaddrs)]

class unpacker(object):
    def __init__(self, buf):
        self._buf = buf
        self._offset = 0
    def __call__(self, fmt):
        s = struct.Struct(fmt)
        result = s.unpack_from(self._buf, self._offset)
        self._offset += s.size
        return result

class PimDm(object):
    def __init__(self):
        self.not_ready_iface_list = []
  
        s_netlink = socket(AF_NETLINK, SOCK_RAW, NETLINK_ROUTE)
        s_netlink.setblocking(False)
        s_netlink.bind((os.getpid(), RTMGRP_IPV6_IFINFO))
        self.s_netlink = s_netlink

    def addInterfaceWhenReady(self):
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
                if rta_data in self.not_ready_iface_list \
                   and rta_data in interfaceUpList():
                    addInterface(rta_data)
                    self.not_ready_iface_list.remove(rta_data)
                break

            unpack._offset += (rta_len - 1) & ~(4 - 1)
  
    def run(self, iface_list, run_path):
        # pim-dm requires interface to be up at startup, 
        # but can handle interfaces going down then up again
        iface_set = set(iface_list)
        up_list = interfaceUpList()
        self.not_ready_iface_list = list(iface_set.difference(up_list))
        ready_iface_list = iface_set.intersection(up_list)

        enabled = (('enabled', True), ('state_refresh', True))
        conf = {
            'PIM-DM': {
                'Interfaces': dict.fromkeys(ready_iface_list, {'ipv6': dict(enabled)}),
            },
            'MLD': {
                'Interfaces': dict.fromkeys(ready_iface_list, dict(enabled[:1])),
            },
        }

        conf_file_path = os.path.join(run_path, 'pim-dm.conf')
        with open(conf_file_path, 'w') as conf_file:
            yaml.dump(conf, conf_file)

        return utils.Popen(['pim-dm', '-config', conf_file_path])

def ifap_iter(ifap):
    '''Iterate over linked list of ifaddrs'''
    ifa = ifap.contents
    while True:
        yield ifa
        if not ifa.ifa_next:
            break
        ifa = ifa.ifa_next.contents

def interfaceUpList():
    ifap = POINTER(struct_ifaddrs)()
    result = _getifaddrs(pointer(ifap))
    if result == -1:
        raise OSError(get_errno())
    elif result == 0:
        pass
    else:
        assert False, result
    del result
    try:
        up_list = []
        for ifa in ifap_iter(ifap):
            if not(ifa.ifa_name in up_list) \
               and ifa.ifa_addr.contents.sa_family == AF_INET6:
                up_list.append(ifa.ifa_name)
        return up_list
    finally:
        _freeifaddrs(ifap)

def addInterface(ifname):
    subprocess.call(['pim-dm', '-6', '-aisr', ifname])
    subprocess.call(['pim-dm', '-aimld', ifname])

def removeInterface(ifname):
    subprocess.call(['pim-dm', '-6', '-ri', ifname])
    subprocess.call(['pim-dm', '-6', '-rimld', ifname])
