==========
 re6stnet
==========

---------------------------------------------
Resilient, Scalable, IPv6 Network application
---------------------------------------------

:Contact: Julien Muchembled <jm@nexedi.com>

Overview
========

re6stnet creates a resilient, scalable, ipv6 network on top of an existing ipv4
network, by creating tunnels on the fly, and then routing targeted traffic
through these tunnels.

re6stnet can be used to:

- guarantee connectedness between computers connected to the
  internet, for which there exists a working route (in case the direct route
  isn't available).
- create large networks
- give ipv6 addresses to machines with only ipv4 available

Building an ipv4 network is also supported if one has software that does not
support ipv6.

How to pronounce `re6st`? Like `resist`.

HOW IT WORKS
============

A re6stnet network consists of at least one server (re6st-registry) and many
nodes (re6stnet). The server is only used to deliver certificates for secure
authentication of peers, and to bootstrap new nodes.
re6stnet can detect and take into account nodes present on the local network.

Resilience
----------
re6stnet guarantees that if there exists a route between two machines,
traffic will be correctly routed between these two machines.
Even if the registry node is down, the probability that the network is not
connected is very low for big enough networks (more than a hundred nodes).

Scalability
-----------

Since nodes don't need to know the whole graph of the network, re6stnet is
easily scalable to tens of thousand of nodes.

Requirements
============

- Python 2.6 or 2.7
- OpenSSL binary and development libraries
- OpenVPN >= 2.3
- Babel_ (with Nexedi patches)
- python-miniupnpc for UPnP support (optional)
- for the demo: miniupnpd_, Graphviz, Screen_, Nemu_

See also `setup.py` for Python dependencies.

.. _Babel: https://lab.nexedi.com/nexedi/babeld
.. _Nemu: https://github.com/thetincho/nemu
.. _miniupnpd: http://miniupnp.free.fr/
.. _Screen: http://savannah.gnu.org/projects/screen

Installation
============

| Official packaging is implemented at
|   https://lab.nexedi.com/nexedi/slapos.package/tree/master/obs/re6st
| and packages are built for many Linux distributions at
|   https://build.opensuse.org/package/show/home:VIFIBnexedi/Re6stnet

| re6stnet is also distributed as a Python egg:
|   https://pypi.python.org/pypi/re6stnet

References
==========

| Building a resilient overlay network : Re6stnet
|   http://www.j-io.org/P-ViFiB-Resilient.Overlay.Network/Base_download
| GrandeNet - The Internet on Steroids
|   https://www.nexedi.com/blog/NXD-Document.Blog.Grandenet.Internet.On.Steroids
| Grandenet success case
|  https://www.nexedi.com/success/erp5-GKR.Success.Case
| n-Order Re6st - Achieving Resiliency and Scaliblity
|  https://www.nexedi.com/blog/NXD-Document.Blog.N.Order.Res6st.Resiliency.And.Scalability

Usage
=====

See ``re6stnet``\ (8) man page.

In order to share the connectivity with others, it is necessary for re6stnet
port ``1194`` to be reachable from outside. If the node has a public IPv4
address, then there is nothing to do, otherwise if UPNP is not already set up
on the gateway:

- If no public IPv4 address but direct access (for example on AWS): add ``ip
  XXX`` where ``XXX`` is the IPv4 public address to ``/etc/re6stnet/re6stnet.conf``.

- If within a LAN: set up an UPNP server on the gateway. See the next section
  for further reference.

You can check connectivity with other re6st nodes of the network with
``netstat -tn | grep 1194``.

Setting up an UPNP server
-------------------------

Sample configuration file for miniupnpd_:

::

  ext_ifname=ppp0
  listening_ip=eth0
  clean_ruleset_interval=600
  allow 1024-65535 192.168.0.0/24 1024-65535
  deny 0-65535 0.0.0.0/0 0-65535

After restarting ``re6stnet`` service on the clients within the LAN, you can
either check ``/var/log/re6stnet.log`` or the ``iptables`` ``NAT`` table to
see that the port ``1194`` is properly redirected, for example:

::

  # iptables -t nat -L -nv
  [...]
  Chain MINIUPNPD (1 references)
  target     prot opt source               destination
  DNAT       tcp  --  anywhere             anywhere             tcp dpt:37194 to:192.168.0.5:1194
  DNAT       tcp  --  anywhere             anywhere             tcp dpt:34310 to:192.168.0.233:1194

Firewall
--------

Sample ``iptables/ip6tables`` rules:

::

  ## IPv4
  iptables -P INPUT DROP
  iptables -P FORWARD DROP
  iptables -P OUTPUT DROP

  iptables -A INPUT -i lo -j ACCEPT
  iptables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
  # re6st
  iptables -A INPUT -p tcp -m tcp --dport 1194 -j ACCEPT
  # UPNP
  iptables -A INPUT -p udp -m udp --sport 1900 -s $GATEWAY_IP -j ACCEPT

  iptables -A OUTPUT -o lo -j ACCEPT
  iptables -A OUTPUT -m state --state NEW,RELATED,ESTABLISHED -j ACCEPT

  ## IPv6
  ip6tables INPUT DROP
  ip6tables FORWARD DROP
  ip6tables OUTPUT DROP

  ip6tables -A INPUT -i lo -j ACCEPT
  ip6tables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
  ip6tables -A INPUT -p udp -m udp --dport babel --src fe80::/10 -j ACCEPT
  # Babel
  ip6tables -A INPUT -i re6stnet+ -p udp -m udp --dport 326 -j ACCEPT
  ip6tables -A INPUT -p ipv6-icmp -m icmp6 --icmpv6-type destination-unreachable -j ACCEPT
  ip6tables -A INPUT -p ipv6-icmp -m icmp6 --icmpv6-type packet-too-big -j ACCEPT
  ip6tables -A INPUT -p ipv6-icmp -m icmp6 --icmpv6-type time-exceeded -j ACCEPT
  ip6tables -A INPUT -p ipv6-icmp -m icmp6 --icmpv6-type parameter-problem -j ACCEPT
  ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT
  ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT
  ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbor-solicitation -m hl --hl-eq 255 -j ACCEPT
  ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbor-advertisement -m hl --hl-eq 255 -j ACCEPT

  ip6tables -A FORWARD -i re6stnet+ -o re6stnet+ -j ACCEPT

  ip6tables -A OUTPUT -o lo -j ACCEPT
  ip6tables -A OUTPUT -m state --state NEW,RELATED,ESTABLISHED -j ACCEPT
  ip6tables -A OUTPUT -p ipv6-icmp -m icmp6 --icmpv6-type destination-unreachable -j ACCEPT
  ip6tables -A OUTPUT -p ipv6-icmp -m icmp6 --icmpv6-type packet-too-big -j ACCEPT
  ip6tables -A OUTPUT -p ipv6-icmp -m icmp6 --icmpv6-type time-exceeded -j ACCEPT
  ip6tables -A OUTPUT -p ipv6-icmp -m icmp6 --icmpv6-type parameter-problem -j ACCEPT
  ip6tables -A OUTPUT -p icmpv6 --icmpv6-type neighbor-solicitation -m hl --hl-eq 255 -j ACCEPT
  ip6tables -A OUTPUT -p icmpv6 --icmpv6-type neighbor-advertisement -m hl --hl-eq 255 -j ACCEPT
