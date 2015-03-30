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
from nemu.iproute import backticks, get_if_data, get_all_route_data, route

def _get_all_route_data():
    ipdata = backticks([IP_PATH, "-o", "route", "list"]) # "table", "all"
    ipdata += backticks([IP_PATH, "-o", "-f", "inet6", "route", "list"])

    ifdata = get_if_data()[1]
    ret = []
    for line in ipdata.split("\n"):
        if line == "":
            continue
        match = re.match(r'(?:(unicast|local|broadcast|multicast|throw|' +
                r'unreachable|prohibit|blackhole|nat) )?' +
                r'(\S+)(?: via (\S+))? dev (\S+).*(?: metric (\d+))?', line)
        if not match:
            raise RuntimeError("Invalid output from `ip route': `%s'" % line)
        tipe = match.group(1) or "unicast"
        prefix = match.group(2)
        nexthop = match.group(3)
        interface = ifdata[match.group(4)]
        metric = match.group(5)
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
