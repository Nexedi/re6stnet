#!/usr/bin/env python
import upnpigd
import openvpn
from configuration import *

(ip, port) = upnpigd.GetExternalInfo(config.LocalPort)
openvpn.LaunchServer()

for (address, port) in config.MandatoryConnections:
	openvpn.LaunchClient(address, port)
