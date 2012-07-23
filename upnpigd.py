import miniupnpc
import socket

# return (address, port)
def ForwardViaUPnP(local_port, protos):
    u = miniupnpc.UPnP()
    u.discoverdelay = 200
    u.discover()
    u.selectigd()
    external_port = 1000

    while True:
        if 'udp' in protos:
            while u.getspecificportmapping(external_port, 'UDP') != None :
                external_port += 1
                if external_port == 65536:
                    raise Exception
        if 'tcp-server' in protos:
            while u.getspecificportmapping(external_port, 'TCP') != None :
                external_port += 1
                if external_port == 65536:
                    raise Exception

        if 'udp' in protos:
            u.addportmapping(external_port, 'UDP', u.lanaddr, local_port,
                'Vifib openvpn server', '')
        if 'tcp-server' in protos:
            u.addportmapping(external_port, 'TCP', u.lanaddr, local_port, 
                'Vifib openvpn server', '')

        print (u.externalipaddress(), external_port)
        return (u.externalipaddress(), external_port)

