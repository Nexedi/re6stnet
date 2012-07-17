import time

def log(message, verbose_level):
    if verbose >= verbose_level:
        print time.strftime("%d-%m-%Y %H:%M:%S : " + message)

def ipFromBin(prefix):
    prefix = hex(int(prefix, 2))[2:]
    ip = ''
    for i in xrange(0, len(prefix) - 1, 4):
        ip += prefix[i:i+4] + ':'
    return ip.rstrip(':')

def ipFromPrefix(vifibnet, prefix, prefix_len):
    prefix = bin(int(prefix))[2:].rjust(prefix_len, '0')
    ip_t = (vifibnet + prefix).ljust(128, '0')
    return ipFromBin(ip_t)
