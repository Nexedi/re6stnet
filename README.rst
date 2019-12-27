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

- Python 2.7
- OpenSSL binary and development libraries
- OpenVPN >= 2.4
- Babel_ (with Nexedi patches)
- geoip2: `python library`_ and `country lite database`_ (optional)
- python-miniupnpc for UPnP support (optional)
- for the demo: miniupnpd_, Graphviz, Screen_, Nemu_, MultiPing_, psutil_

See also `setup.py` for Python dependencies.

.. _Babel: https://lab.nexedi.com/nexedi/babeld
.. _Nemu: https://github.com/thetincho/nemu
.. _miniupnpd: http://miniupnp.free.fr/
.. _MultiPing: https://github.com/romana/multi-ping
.. _psutil: https://pypi.org/project/psutil/
.. _Screen: http://savannah.gnu.org/projects/screen
.. _python library: https://pypi.org/project/geoip2/
.. _country lite database: https://dev.maxmind.com/geoip/geoip2/geolite2/

Installation
============

Packages (preferred method)
---------------------------

We are providing a `re6st-node` package for many distributions.
In order to install it, go to

  https://build.opensuse.org/package/show/home:VIFIBnexedi/Re6stnet

and find your distribution on the build result at the right of the page.
Once you have your distribution name <DISTRIB_NAME>, the repository to add is

  http://download.opensuse.org/repositories/home:/VIFIBnexedi/<DISTRIB_NAME>

For example (as root):

* Ubuntu 16.04::

   echo "deb http://download.opensuse.org/repositories/home:/VIFIBnexedi/xUbuntu_16.04 ./" >/etc/apt/sources.list.d/re6stnet.list
   wget -qO - https://download.opensuse.org/repositories/home:/VIFIBnexedi/xUbuntu_16.04/Release.key |apt-key add -

* Debian 9::

   echo "deb http://download.opensuse.org/repositories/home:/VIFIBnexedi/Debian_9.0 ./" >/etc/apt/sources.list.d/re6stnet.list
   wget -qO - https://download.opensuse.org/repositories/home:/VIFIBnexedi/Debian_9.0/Release.key |apt-key add -

Then::

  apt update
  apt install re6st-node

| The packaging is maintained at
|   https://lab.nexedi.com/nexedi/slapos.package/tree/master/obs/re6st

Python egg
----------

| re6stnet is also distributed as a Python egg:
|   https://pypi.org/project/re6stnet/

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
