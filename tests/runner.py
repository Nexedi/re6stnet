import sys
import os
import unittest
import time
from StringIO import StringIO
import json
from . import *



class TestResult(unittest.TextTestResult):
    def startTestRun(self):
        self.start = time.time()


    def stopTestRun(self):
        """ custom report dict"""
        self.end = time.time()
        self.report = dict(test_count = self.testsRun, 
                            error_count = len(self.errors),
                            failure_count = len(self.failures),
                            skip_count = len(self.skipped),
                            duration =  round(self.end - self.start, 2),
                            date = time.strftime("%Y/%m/%d %H:%M:%S", time.gmtime(self.start))
        )


class runner(unittest.TextTestRunner):
    def _makeResult(self):
        return TestResult(self.stream, self.descriptions, self.verbosity)


def main():

    test_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(test_dir)
    test_case = {name: mod for name, mod in globals().items() if name.split('_',1)[0] == 'test'}
    result = {}
    for case, mod in test_case.items(): 
        suite = unittest.TestLoader().loadTestsFromModule(mod)
        err = StringIO()
        result[case] = runner(stream=err, verbosity=3).run(suite).report
        result[case]['stderr'] = err.getvalue()
        sys.stderr.write(err.getvalue())
        err.close()

    print json.dumps(result)


if __name__ == "__main__":
    main()