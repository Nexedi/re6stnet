import sqlite3, subprocess

def getConfig(db, name):
    r, = next(db.execute(
              "SELECT value FROM config WHERE name=?", (name,)), (None,))
    if r is not None:
        r = str(r).encode('hex')
    return r

def getCurrentHmacs(db):
    true_hmacs = {'babel_hmac0': None, 'babel_hmac1': None, 'babel_hmac2': None}
    for k in true_hmacs.keys():
        true_hmacs[k] = getConfig(db, k)
    return true_hmacs

def killRe6st(machine):
    p = subprocess.Popen(['pgrep', '-f', 'set ./py re6stnet @%s' %machine],
                         stdout=subprocess.PIPE)
    ps_id = p.communicate()[0].split('\n', 1)[0]
    if ps_id:
        subprocess.Popen(['kill', ps_id])
        print 'killed re6st on ' + machine

def checkHMAC(db, machines):
    hmac = getCurrentHmacs(db)
    print hmac
    rc = True
    ps = subprocess.Popen(['pgrep', '-a', 'babel'], stdout=subprocess.PIPE)
    for p in (p for p in ps.communicate()[0].split('\n') if p):
        if p.split('/',1)[0].split()[-1] in machines:
            if hmac['babel_hmac0'] and not hmac['babel_hmac1']: # state = hmac0
                if ('hmac_sign' not in p or
                   'hmac_accept' in p or
                    p.split('hmac_sign value ',1)[1].split()[0]\
                      != hmac['babel_hmac0']):
                    rc = False
                    print 'HMAC config wrong in %s' % p
            else:
                if hmac['babel_hmac0']: # state = hmac0 and hmac1
                    sign = 0
                    accept = 1
                else: # state = hmac1 and hmac2
                    sign = 1
                    accept = 2
                if ('hmac_accept' not in p or
                   'hmac_sign' not in p or
                    p.split('hmac_sign value ',1)[1].split()[0] != hmac[sign] or
                    p.split('hmac_accept value ',1)[1].split()[0] != hmac[acc]):
                    rc = False
                    print 'HMAC config wrong in %s' % p
    if rc:
        print('Babel OK')
    return rc
