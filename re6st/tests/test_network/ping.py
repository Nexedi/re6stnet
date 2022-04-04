# -*- coding: utf-8 -*-
'''
Script launched on machines from the demo with the option -p/--ping
It uses Multiping to ping several IPs passed as arguments.
After Re6st is stable, this script logs when it does not get response from a
machine in a csv file stored in the directory of the machine in this format:
time, sequence number, number of non-responding machines, ip of these machines
'''
import argparse, errno, socket, time, sys
from multiping import MultiPing

PING_INTERVAL = 10
PING_TIMEOUT = 4

class MultiPing(MultiPing):
    # Patch of Multiping because it stays blocked to ipv4
    # emission when we want to ping only ipv6 addresses.
    # So we only keep the ipv6 part for the demo.
    # Bug issued: https://github.com/romana/multi-ping/issues/22
    def _read_all_from_socket(self, timeout):
        pkts = []
        if self._ipv6_address_present:
            try:
                self._sock6.settimeout(timeout)
                while True:
                    p = self._sock6.recv(128)
                    pkts.append((bytearray(p), time.time()))
                    self._sock6.settimeout(0)
            except socket.timeout:
                pass
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK:
                    pass
                else:
                    raise
        return pkts

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', nargs = '+', help = 'the list of addresses to ping')
    parser.add_argument('--retry', action='store_true', help='retry ping unitl success')
    
    args = parser.parse_args()
    addrs = args.a
    retry = args.retry

    while True:
        mp = MultiPing(addrs)
        mp.send()
        _, no_responses = mp.receive(PING_TIMEOUT)
        
        if retry and no_responses:
            continue
        else:
            sys.stdout.write(" ".join(no_responses))
            return


if __name__ == '__main__':
    main()
