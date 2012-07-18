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
		while u.getspecificportmapping(externalPort, 'UDP') != None:
			externalPort = max(externalPort + 1, 49152)
			if externalPort == 65536:
				raise Exception
		if u.addportmapping(externalPort, 'UDP', u.lanaddr, localPort, 'Vifib openvpn server', ''):
			return (u.externalipaddress(), externalPort)

# TODO : specify a lease duration
