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

def checkHMAC(db, machines):
    hmac = getCurrentHmacs(db)
    rc = True
    ps = subprocess.Popen(['pgrep', '-a', 'babel'], stdout=subprocess.PIPE)
    for p in (p for p in ps.communicate()[0].split('\n') if p):
        if p.split('/',1)[0].split()[-1] in machines:
            if hmac['babel_hmac0'] and not hmac['babel_hmac1']: # state = hmac0
                if ('sign' not in p or
                    'accept' in p or
                    p.split('sign value ',1)[1].split()[0]\
                      != hmac['babel_hmac0']):
                    rc = False
                    print 'HMAC config wrong for in %s' % p
            else:
                if hmac['babel_hmac0']: # state = hmac0 and hmac1
                    sign = 'babel_hmac0'
                    accept = 'babel_hmac1'
                else: # state = hmac1 and hmac2
                    sign = 'babel_hmac1'
                    accept = 'babel_hmac2'
                if ('accept' not in p or
                    'sign' not in p or
                    p.split('sign value ',1)[1].split()[0] != hmac[sign] or
                    p.split('accept value ',1)[1].split()[0] != hmac[accept]):
                    rc = False
                    print 'HMAC config wrong in %s' % p
    if rc:
        print('Babel OK')
    return rc
