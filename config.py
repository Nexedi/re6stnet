import socket

hostname = socket.gethostname()

CaPath = '/root/overnet/keys/ca.crt'
CertPath = '/root/overnet/keys/server.crt'
KeyPath = '/root/overnet/keys/server.key'
DhPath = '/root/overnet/keys/dh1024.pem'

if hostname == 'm5':
	IPv6 = '2000:0:0:1::1/64'
	MandatoryConnections = [('10.1.4.3', 1194)]
elif hostname == 'm6':
	IPv6 = '2000:0:0:2::1/64'

Debug = True
