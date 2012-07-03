def CheckVarExists(varName):
        return  varName in config.__dict__

def FailIfNotExists(varName):
        if not CheckVarExists(varName):
                print 'Entry ' + varName + ' not found in config.py'
                sys.exit(-1)


def SetIfNotExists(varName, value):
        if not CheckVarExists(varName):
                config.__dict__[varName] = value

# Check that the file config.py exist and is valid
try:
        import config
except ImportError:
        print 'Unable to read the config file config.py'
        sys.exit(-1)

# Check vars existence
FailIfNotExists('CaPath')
FailIfNotExists('CertPath')
FailIfNotExists('KeyPath')
FailIfNotExists('DhPath')
FailIfNotExists('IPv6')

SetIfNotExists('Debug', False)
SetIfNotExists('MandatoryConnections', [])
SetIfNotExists('LocalPort', 1194)
