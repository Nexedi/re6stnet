import miniupnpc
import socket

# return (address, port)
def ForwardViaUPnP(local_port):
    u = miniupnpc.UPnP()
    u.discoverdelay = 200
    u.discover()
    u.selectigd()
    external_port = 1194
    while True:
        while u.getspecificportmapping(external_port, 'UDP') != None:
            external_port = max(externalPort + 1, 49152)
            if external_port == 65536:
                raise Exception
        if u.addportmapping(external_port, 'UDP', u.lanaddr, local_port, 'Vifib openvpn server', ''):
            return (u.externalipaddress(), external_port)

