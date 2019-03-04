# -*- coding: utf-8 -*-
'''
Script launched on machines from the demo with the option -p/--ping
It uses Multiping to ping several IPs passed as an argument.
After Re6st is stable, logs when it does not get response from a machine
in a csv file stored in the directory of the machine under this format:
time, sequence number, number of non-responding machines, ip of these machines
'''
import argparse, errno, logging, os, socket, time
from multiping import MultiPing
from threading import Thread, Lock

PING_EVERY = 0.1
PING_TIMEOUT = 4
csv_lock = Lock()

class MultiPing(MultiPing):
    # Patch of Multiping because it stays blocked to ipv4
    # emission when we want to ping only ipv6 addresses.
    # So we only keep the ipv6 part for the demo.
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

class Ping(Thread):

    seq = None
    seq_lock = Lock()

    def run(self):
        global no_resp,current_time,index
        mp = MultiPing(addrs)
        assert mp._last_used_id is None
        cls = self.__class__
        with cls.seq_lock:
            mp._last_used_id = cls.seq
            mp.send()
            seq=cls.seq = mp._last_used_id
        responses, no_responses = mp.receive(PING_TIMEOUT)
        x = list(responses)
        x += no_responses
        assert sorted(x) == sorted(addrs), (addrs, responses, no_responses)
        with csv_lock:
            if no_responses:
                my_csv.write("%r,%d,%d,%s\n"%(time.time(),seq,
                            len(no_responses),' '.join(no_responses)))
                my_csv.flush()
            else :
                # Update modification/access time of csv
                os.utime(csv_path,(time.time(),time.time()))

        for add in no_responses:
            print("No response from %s with seq no %d" %(add,seq))

parser = argparse.ArgumentParser()
parser.add_argument("n", help="my machine name (m1,m2...)")
parser.add_argument('a', nargs='+', help="the list of addresses to ping")
args = parser.parse_args()
my_name = args.n
addrs = args.a

print("Waiting for every machine to answer ping..")
while True:
    mp = MultiPing(addrs)
    mp.send()
    _, no_responses = mp.receive(0.5)
    if not no_responses:
        break
    # Currently useless because MultiPing does not return earlier if it
    # couldn't send any ping (e.g. no route to host). Let's hope it will
    # improve.
    time.sleep(0.1)
print('Network is stable, starting to ping..')

csv_path='{}/ping_logs.csv'.format(my_name)
my_csv = open(csv_path,"w+")
my_csv.write("%r,%s,%d\n"%(time.time(),0,0))
my_csv.flush()

while True:
    Ping().start()
    time.sleep(0.1)
