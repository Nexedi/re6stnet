# -*- coding: utf-8 -*-
import argparse, errno, logging, os, socket, sqlite3, subprocess, time
from multiping import MultiPing
from threading import Thread, Lock

INIT_TIME = 30
PING_TIMEOUT = 4
ADDRS = ['2001:db8:42::1', '2001:db8:42:1::1', '2001:db8:42:2::',
         '2001:db8:42:3::1', '2001:db8:42:4::1', '2001:db8:42:5::1',
         '2001:db8:42:6::1', '2001:db8:42:7::1', '2001:db8:42:8::1']
MACHINES = ['registry', 'm1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8']

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

def launchRegistry():
    print 'launch registry'
    p = subprocess.Popen("python ./py re6st-registry @registry/re6st-registry.conf --db registry/registry.db --mailhost /home/killian/re6stnet/demo/mbox -v4".split())
    return p

def launchMachine(machine):
    #TODO
    print 'start re6st on machine %s' % machine

def stopRegistry(p):
    print 'stop re6st-registry'
    if p:
        p.kill
    else:
        subprocess.Popen("pkill -f re6st-registry".split())

def stopMachine(machine):
    #TODO
    print 'stop re6st on machine %s' % machine
    return subprocess.check_output(["pgrep", "-a", "-f", "python", "./py", "re6stnet", " @%s"  % machine])

def replaceHMAC():
    print 'generate new HMAC in registry.db'
    rand = os.urandom(32)
    db.execute("INSERT OR REPLACE INTO config VALUES ('babel_hmac_rand', ?)",
                                                     (rand,))
    return rand

def checkHMAC(machines, hmac, step):
    found_wrong_hmac = False
    for mach in machines:
        db = sqlite3.connect('%s/cache.db' % mach, isolation_level=None)
        db.text_factory = str
        selected_hmac, = next(db.execute(
            "SELECT value FROM config WHERE name='babel_hmac_rand'"), None)
        if str(selected_hmac) != str(hmac):
            found_wrong_hmac = True
            print 'step %d: current hmac in registry.db = %s' % (step, hmac)
            print 'step %d: hmac found in cache.db of %s: %s' % (step, mach, selected_hmac)
        db.close()
    if not found_wrong_hmac:
        print 'step %d: all HMAC in cache.db are correct' % step

def pingFromRegistry(step):
    mp = MultiPing(ADDRS)
    mp.send()
    _, no_resp = mp.receive(PING_TIMEOUT)
    if no_resp:
        print 'step %d: no answer from %s' % (step, no_resp)

db = sqlite3.connect('registry/registry.db', isolation_level=None)
db.text_factory = str

#START OF THE TEST
time.sleep(INIT_TIME) #wait for re6st to initialize
#print stopMachine('m3')
pingFromRegistry(step=0) #check that machines answer
stopRegistry(None)
hmac = replaceHMAC() #change HMAC for the first time
time.sleep(5)
p = launchRegistry() #all machines should receive the new HMAC after launch
time.sleep(10) #we let them the time to get the conf
checkHMAC(MACHINES, hmac, step=1) #check that machines have the correct HMAC in their db
time.sleep(10)
p.kill()
#print stopMachine('m2')
time.sleep(5)
p = launchRegistry()
