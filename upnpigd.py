#!/usr/bin/env python
import miniupnpc
import socket

# return (address, port)
def ForwardViaUPnP(localPort):
	u = miniupnpc.UPnP()
	u.discoverdelay = 200
	u.discover()
	u.selectigd()
	externalPort = 1194
	while True:
		while u.getspecificportmapping(externalPort, 'TCP') != None:
			externalPort = max(externalPort + 1, 49152)
			if externalPort == 65536:
				raise Exception
		if u.addportmapping(externalPort, 'UDP', u.lanaddr, localPort, 'Vifib openvpn server', ''):
			return (u.externalipaddress(), externalPort)

# TODO : specify a lease duration
# TODO : use more precises exceptions
# TODO : be sure that GetLocalIp do not bug

def GetLocalIp():
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	s.connect(('10.8.8.8', 0))
	return s.getsockname()[0]


def GetExternalInfo(localPort):
	try:
		return  ForwardViaUPnP(localPort)
	except Exception:
		return (GetLocalIp(), localPort)

