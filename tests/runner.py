import sys
import os
import unittest
import time
import json
from .test_registry import TestRegistrtServer


class TestResult(unittest.TextTestResult):
    def startTestRun(self):
        self.start = time.time()


    def stopTestRun(self):
        self.end = time.time()
        self.report = dict(test_count = self.testsRun, 
                            error_count = len(self.errors),
                            failure_count = len(self.failures),
                            skip_count = len(self.skipped),
                            duration =  round(self.end - self.start, 2)
        )

 

class runner(unittest.TextTestRunner):
    def _makeResult(self):
        return TestResult(self.stream, self.descriptions, self.verbosity)


def main():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(test_dir)
    suite = unittest.TestSuite()
    for method in dir(TestRegistrtServer):
       if method.startswith("test"):
          suite.addTest(TestRegistrtServer(method))
    result = runner().run(suite)
    print json.dumps(result.report)
    

if __name__ == "__main__":
    main()