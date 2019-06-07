import sqlite3, subprocess

MACHINES = {'m1': '2001:db8:42:1::1', 'm2': '2001:db8:42:2::1',
            'm3': '2001:db8:42:3::1', 'm4': '2001:db8:42:4::1',
            'm5': '2001:db8:42:5::1', 'm6': '2001:db8:42:6::1',
            'm7': '2001:db8:42:7::1', 'm8': '2001:db8:42:8::1',
            'registry': '2001:db8:42::1'}

reg_db = sqlite3.connect('registry/registry.db', isolation_level=None,
                                                 check_same_thread=False)
reg_db.text_factory = str
network = '001000000000000100001101101110000000000001000010'

def getConfig(db, name):
    r, = next(db.execute(
              "SELECT value FROM config WHERE name=?", (name,)), (None,))
    if r is not None:
        r = str(r).encode('hex')
    return r

def getCurrentHmacs():
    true_hmacs = {'babel_hmac0': None, 'babel_hmac1': None, 'babel_hmac2': None}
    for k in true_hmacs.keys():
        true_hmacs[k] = getConfig(reg_db, k)
    return true_hmacs

def checkDB(machines=MACHINES):
    rc = True
    true_hmacs = getCurrentHmacs()
    for m in machines.keys():
        db = sqlite3.connect('%s/cache.db' % m, isolation_level=None,
                                                check_same_thread=False)
        for k in true_hmacs.keys():
            r = getConfig(db, k)
            if not r and true_hmacs[k]:
                print('missing %s in db of %s' % (k, m))
                rc = False
            elif r:
                if true_hmacs[k] and true_hmacs[k] != r:
                    print('%s of %s is %s (!= %s)' % (k, m, r, true_hmacs[k]))
                    rc = False
                elif not true_hmacs[k]:
                    print('db of %s should not contain %s' %(m, k))
                    rc = False
        db.close()
        if rc:
            print('Databases OK')
        return rc

def checkBabel(machines=MACHINES):
    hmacs = getCurrentHmacs()
    for k, v in hmacs.iteritems():
        if v and v is not '':
            hmacs[k] = '%064x' % int(bin(len(network))[2:].zfill(7) + network +
                                     bin(int(v,16))[9+len(network):],2)
    rc = True
    ps = subprocess.Popen(['pgrep', '-a', 'babel'], stdout=subprocess.PIPE)
    for p in (p for p in ps.communicate()[0].split('\n') if p):
        for k, v in hmacs.iteritems():
            k = k[6:]
            if v and v is not '':
                # should find key
                if '%s value ' % k not in p:
                    print('missing %s in %s' % (k, p))
                    rc = False
                elif p.split('%s value ' % k,1)[1].split()[0] != v:
                    print('%s should be %s in %s' % (k, v, p))
                    rc = False
                b0 = 'babel_hmac0'; b1 = 'babel_hmac1'; b2 = 'babel_hmac2'
                if ((k is hmacs[b0] and not hmacs[b1] and not hmacs[b2]) or
                    (k is hmacs[b0] and hmacs[b1] and not hmacs[b0]) or
                    (k is hmacs[b1] and hmacs[b2] and not hmacs[b0])):
                    if 'hmac %s' % k not in p:
                        print('Missing use of %s in %s' % (k, p))
                        rc = False
            elif v is '':
                # should find ignore_no_hmac
                if 'ignore_no_hmac' not in p:
                    print('missing ignore_no_hmac in %s' % p)
                    rc = False
            else:
                # should not find key
                if k in p:
                    print('%s should not be in %s' % (k, p))
                    rc = False
    if rc:
        print('Babel OK')
    return rc
