import argparse, subprocess, time
'''
This script logs the output of traceroute with ICMP to several machines
passed as arguments, it is used to check if a machine from one re6st
network contacts a machine from another re6st network via its BGP
(its registry) and therefore internet or directly via a machine from
its own re6st network (which is not ok).
The log file 'traceroute.csv' follows this pattern:
timestamp | first hop->...->last hop (destination) | ok OR error
The script will fail traceroute while re6st initializes (~30s)
'''
parser = argparse.ArgumentParser()
parser.add_argument('n', help = 'my machine name (m1,m2...)')
parser.add_argument('a', nargs = '+', help = 'addresses to check routes to')
args = parser.parse_args()
me = args.n
addrs = args.a

csv = open(me + '/traceroute.csv','w')

while True:
    for add in addrs:
        try:
            hops = subprocess.check_output(['traceroute6', '-n', '-I',  add])
            if '* * *' in hops:
                break
            hops = [ hop for hop in hops.split() if '2001' in hop ]
            if hops:
                #the first two occurences are verbose of traceroute
                #that says who we want to reach, they're not hops
                hops = '->'.join(hops[2:])
            else:
                break
            csv.write('%r,%s,%s\n' % (time.time(), hops,
                      'ok' if '2001:db8::1' in hops else 'error'))
            csv.flush()
            time.sleep(1)
        except:
            print('Traceroute failed, trying again in 10s')
            time.sleep(10)
