# -*- coding: utf-8 -*-

# Copyright 2010, 2011 INRIA
# Copyright 2011 Martín Ferrari <martin.ferrari@gmail.com>
#
# This file is contains patches to Nemu.
#
# Nemu is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2, as published by the Free
# Software Foundation.
#
# Nemu is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# Nemu.  If not, see <http://www.gnu.org/licenses/>.

import re
import os
from new import function
from nemu.iproute import backticks, get_if_data, route, \
    get_addr_data, get_all_route_data, interface
from nemu.interface import Switch, Interface

def _get_all_route_data():
    ipdata = backticks([IP_PATH, "-o", "route", "list"]) # "table", "all"
    ipdata += backticks([IP_PATH, "-o", "-f", "inet6", "route", "list"])

    ifdata = get_if_data()[1]
    ret = []
    for line in ipdata.split("\n"):
        if line == "":
            continue
        # PATCH: parse 'from'
        # PATCH: 'dev' is missing on 'unreachable' ipv4 routes
        match = re.match('(?:(unicast|local|broadcast|multicast|throw|'
            r'unreachable|prohibit|blackhole|nat) )?(\S+)(?: from (\S+))?'
            r'(?: via (\S+))?(?: dev (\S+))?.*(?: metric (\d+))?', line)
        if not match:
            raise RuntimeError("Invalid output from `ip route': `%s'" % line)
        tipe = match.group(1) or "unicast"
        prefix = match.group(2)
        #src = match.group(3)
        nexthop = match.group(4)
        interface = ifdata[match.group(5) or "lo"]
        metric = match.group(6)
        if prefix == "default" or re.search(r'/0$', prefix):
            prefix = None
            prefix_len = 0
        else:
            match = re.match(r'([0-9a-f:.]+)(?:/(\d+))?$', prefix)
            prefix = match.group(1)
            prefix_len = int(match.group(2) or 32)
        ret.append(route(tipe, prefix, prefix_len, nexthop, interface.index,
            metric))
    return ret

get_all_route_data.func_code = _get_all_route_data.func_code

interface__init__ = interface.__init__
def __init__(self, *args, **kw):
    interface__init__(self, *args, **kw)
    if self.name:
        self.name = self.name.split('@',1)[0]
interface.__init__ = __init__

get_addr_data.orig = function(get_addr_data.func_code,
                              get_addr_data.func_globals)
def _get_addr_data():
    byidx, bynam = get_addr_data.orig()
    return byidx, {name.split('@',1)[0]: a for name, a in bynam.iteritems()}
get_addr_data.func_code = _get_addr_data.func_code

@staticmethod
def _gen_if_name():
    n = Interface._gen_next_id()
    # Max 15 chars
    return "NETNSif-" + ("%.4x%.3x" % (os.getpid(), n))[-7:]
Interface._gen_if_name = _gen_if_name

@staticmethod
def _gen_br_name():
    n = Switch._gen_next_id()
    # Max 15 chars
    return "NETNSbr-" + ("%.4x%.3x" % (os.getpid(), n))[-7:]
Switch._gen_br_name = _gen_br_name