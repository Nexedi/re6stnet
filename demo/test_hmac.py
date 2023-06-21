from binascii import b2a_hex
import psutil

BABEL_HMAC = 'babel_hmac0', 'babel_hmac1', 'babel_hmac2'

def getConfig(db, name):
    r = db.execute("SELECT value FROM config WHERE name=?", (name,)).fetchone()
    if r:
        return b2a_hex(*r)

def killRe6st(node):
    for p in psutil.Process(node._screen.pid).children():
        if p.cmdline()[-1].startswith('set ./py re6stnet '):
            p.kill()
            break

def checkHMAC(db, machines):
    hmac = [getConfig(db, k) for k in BABEL_HMAC]
    rc = True
    for x in psutil.Process().children(True):
        if x.name() == 'babeld':
            sign = accept = None
            args = x.cmdline()
            for x in args:
                if x.endswith('/babeld.log'):
                    if x[:-11] not in machines:
                        break
                elif x.startswith('key '):
                    x = x.split()
                    if 'sign' in x:
                        sign = x[-1]
                    elif 'accept' in x:
                        accept = x[-1]
            else:
                i = 0 if hmac[0] else 1
                if hmac[i] != sign or hmac[i+1] != accept:
                    print('HMAC config wrong for in %s' % args)
                    rc = False
    if rc:
        print('All nodes use Babel with the correct HMAC configuration')
    else:
        print('Expected config: %s' % dict(zip(BABEL_HMAC, hmac)))
    return rc
