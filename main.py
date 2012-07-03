import upnpigd
from subprocess import call
from configuration import *

# Call == bad !!
# TODO : use subprocess module

def LaunchOpenVpnClient(serverAddress, serverPort):
	call(['openvpn', 
		'--client',
		'--dev', 'tun',
		'--proto', 'udp',
		'--remote', serverAddress, str(serverPort),
		'--nobind',
		'--persist-key',
		'--persist-tun',
		'--ca', config.CaPath,
		'--cert', config.CertPath,
		'--key', config.KeyPath,
		'--ns-cert-type', 'server',
		'--comp-lzo',
		'--verb', '3',
		'--daemon', 'openVpnClient(' + serverAddress + ')' ])

def LaunchOpenVpnServer(port):
	call(['openvpn',
		'--dev', 'tun',
		'--proto', 'udp',
		'--ca', config.CaPath,
                '--cert', config.CertPath,
                '--key', config.KeyPath,
		'--dh', config.DhPath,
		'--server', config.Subnet, config.SubnetMask,
		'--port', str(port),
		'--ifconfig-pool-persist', 'ipp.txt',
		'--comp-lzo',
		'--keepalive', '10', '120',
		'--persist-tun',
		'--persist-key',
		'--verb', '3'])

