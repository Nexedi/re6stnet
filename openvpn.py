from subprocess import call
from configuration import *

def LaunchClient(serverAddress, serverPort):
	if config.Debug:
		print 'Connecting to :' + serverAddress
        call(['openvpn',
                '--client',
                '--dev', 'tap',
                '--proto', 'udp',
                '--remote', serverAddress, str(serverPort),
                '--nobind',
		'--script-security', '2',
		'--up', './up-client',
                '--persist-key',
                '--persist-tun',
		'--tls-client',
                '--ca', config.CaPath,
                '--cert', config.CertPath,
                '--key', config.KeyPath,
                '--user', 'nobody',
		'--verb', '3',
		'--daemon', 'openVpnClient(' + serverAddress + ')' ])

def LaunchServer():
        call(['openvpn',
		'--dev', 'tap',
		'--mode', 'server',
                '--proto', 'udp',
		'--tls-server',
                '--ca', config.CaPath,
                '--cert', config.CertPath,
                '--key', config.KeyPath,
                '--dh', config.DhPath,
		'--user', 'nobody',
                '--port', str(config.LocalPort),
		'--up', './up-server ' + config.IPv6,
		'--script-security', '2',
                '--persist-tun',
                '--persist-key',
		'--daemon', 'openvpnServer',
		'--verb', '3'])


# TODO : should we use comp-lzo option ?
# TODO : group nobody
