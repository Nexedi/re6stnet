import os, struct, subprocess, time, yaml
from ctypes import (
    Structure, Union, POINTER,
    pointer, c_ushort, c_byte, c_void_p, c_char_p, c_uint, c_int,
    CDLL, util as ctypes_util,
)
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

libc = CDLL(ctypes_util.find_library('c'), use_errno=True)
getifaddrs = libc.getifaddrs
getifaddrs.restype = c_int
getifaddrs.argtypes = [POINTER(POINTER(struct_ifaddrs))]
freeifaddrs = libc.freeifaddrs
freeifaddrs.restype = None
freeifaddrs.argtypes = [POINTER(struct_ifaddrs)]

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
        s_netlink = socket(AF_NETLINK, SOCK_RAW, NETLINK_ROUTE)
        s_netlink.setblocking(False)
        s_netlink.bind((os.getpid(), RTMGRP_IPV6_IFINFO))
        self.s_netlink = s_netlink

        self.started = False
        self._next_refresh = time.time()

    def addInterface(self, ifname):
        while not self.isStarted():
            time.sleep(0.5)
        subprocess.call(['pim-dm', '-6', '-aisr', ifname])
        subprocess.call(['pim-dm', '-aimld', ifname])

    def addInterfaceWhenReady(self):
        if not self.not_ready_iface_set:
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
            rta_data = unpack("%ds" % rta_len)[0].rstrip('\0\n\1')

            if rta_type == IFLA_IFNAME:
                if rta_data in self.not_ready_iface_set \
                   and rta_data in interfaceUpSet():
                    self.addInterface(rta_data)
                    self.not_ready_iface_set.remove(rta_data)
                break

            unpack._offset += (rta_len - 1) & ~(4 - 1)

    def isStarted(self):
        if not self.started:
            self.started = os.path.exists('/run/pim-dm/0')
        return self.started

    def refresh(self):
        self._next_refresh = time.time() + 5 if self.not_ready_iface_set else None

    def run(self, iface_list, run_path):
        # pim-dm requires interface to be up at startup, 
        # but can handle interfaces going down then up again
        iface_set = set(iface_list)
        up_set = interfaceUpSet()
        self.not_ready_iface_set = iface_set - up_set
        iface_set &= up_set

        enabled = (('enabled', True), ('state_refresh', True))
        conf = {
            'PIM-DM': {
                'Interfaces': dict.fromkeys(iface_set, {'ipv6': dict(enabled)}),
            },
            'MLD': {
                'Interfaces': dict.fromkeys(iface_set, dict(enabled[:1])),
            },
        }

        conf_file_path = os.path.join(run_path, 'pim-dm.conf')
        with open(conf_file_path, 'w') as conf_file:
            yaml.dump(conf, conf_file)

        return utils.Popen(['pim-dm', '-config', conf_file_path])

    def select(self, r, w, t):
        r[self.s_netlink] = self.addInterfaceWhenReady
        if self._next_refresh:
            t.append((self._next_refresh, self.refresh))

def ifap_iter(ifa):
    '''Iterate over linked list of ifaddrs'''
    while ifa:
        ifa = ifa.contents
        yield ifa
        ifa = ifa.ifa_next

def interfaceUpSet():
    ifap = POINTER(struct_ifaddrs)()
    getifaddrs(pointer(ifap))
    try:
        return {
            ifa.ifa_name
            for ifa in ifap_iter(ifap)
            if ifa.ifa_addr and ifa.ifa_addr.contents.sa_family == AF_INET6
        }
    finally:
        freeifaddrs(ifap)
