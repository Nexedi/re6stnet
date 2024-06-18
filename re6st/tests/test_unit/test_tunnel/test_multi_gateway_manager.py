#!/usr/bin/env python3
import os
import sys
import unittest
from mock import patch

from re6st import tunnel


class testMultGatewayManager(unittest.TestCase):
    
    def setUp(self):
        self.manager = tunnel.MultiGatewayManager(lambda x:x+x)
        patcher = patch("subprocess.check_call")
        self.addCleanup(patcher.stop)
        self.sub = patcher.start()

    @patch("logging.trace", create=True)
    def test_add(self, log_trace):
        """add new dest twice"""
        dest = "dest"

        self.manager.add(dest, True)
        self.manager.add(dest, True)

        self.assertEqual(self.manager[dest][1], 1)
        self.sub.assert_called_once()
        cmd = log_trace.call_args[0][1]
        self.assertIn(dest+dest, cmd)
        self.assertIn("add", cmd)


    def test_add_null_route(self):
        """ add two dest which don't call ip route"""
        dest1 = "dest1"
        dest2 = ""

        self.manager.add(dest1, False)
        self.manager.add(dest2, True)

        self.sub.assert_not_called()


    @patch("logging.trace", create=True)
    def test_remove(self, log_trace):
        "remove a dest twice"
        dest = "dest"
        gw = "gw"
        self.manager[dest] = [gw,1]

        self.manager.remove(dest)
        self.assertEqual(self.manager[dest][1], 0)

        self.manager.remove(dest)

        self.sub.assert_called_once()
        self.assertIsNone(self.manager.get(dest))
        cmd = log_trace.call_args[0][1]
        self.assertIn(gw, cmd)
        self.assertIn("del", cmd)
        
    
    def test_remove_null_gw(self):
        """ remove a dest which don't have gw"""
        dest = "dest"
        gw = ""
        self.manager[dest] = [gw, 0]

        self.manager.remove(dest)
        
        self.assertIsNone(self.manager.get(dest))
        self.sub.assert_not_called()


if __name__ == "__main__":
    unittest.main()