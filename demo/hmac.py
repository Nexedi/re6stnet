import sqlite3, subprocess

MACHINES = {'m1': '2001:db8:42:1::1', 'm2': '2001:db8:42:2::1',
            'm3': '2001:db8:42:3::1', 'm4': '2001:db8:42:4::1',
            'm5': '2001:db8:42:5::1', 'm6': '2001:db8:42:6::1',
            'm7': '2001:db8:42:7::1', 'm8': '2001:db8:42:8::1',
            'registry': '2001:db8:42::1'}

reg_db = sqlite3.connect('registry/registry.db', isolation_level=None)
reg_db.text_factory = str

def getConfig(self, db, name):
    r, = next(db.execute(
              "SELECT value FROM config WHERE name=?", (name,)), None)
    return r

def checkDB(self, machines=MACHINES):
    true_hmacs = {'hmac0': None, 'hmac1': None, 'hmac2': None}
    for k in true_hmacs.keys():
        true_hmac[k] = self.getConfig(self.reg_db, k)
    for m in machines.keys():
        db = sqlite3.connect('%s/cache.db', isolation_level=None)
        for k in true_hmacs.keys():
            r = getConfig(db, k)
            if not r and true_hmacs[k]:
                print('no %s found in db of %s' % (k, m))
            elif r:
                if true_hmacs[k] and true_hmacs[k] is not r:
                    print('%s of %s is %s (!= %s)' % (k, m, r, true_hmacs[k]))
                elif not true_hmacs[k]:
                    print('db of %s should not contain %s' %(m, k))
checkDB(MACHINES)
