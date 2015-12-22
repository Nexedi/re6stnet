%define _builddir %(pwd)
%define ver %(python re6st/version.py)

Summary:    resilient, scalable, IPv6 network application
Name:       re6stnet
Version:    %(set %ver; echo ${1%%-*})
Release:    %(set %ver; echo ${1#*-})
License:    GPLv2+
Group:      Applications/Internet
BuildArch:  noarch
Requires:   babeld = 1.6.2-nxd1
Requires:   iproute
Requires:   openssl
Requires:   openvpn >= 2.3
Requires:   python >= 2.7
Requires:   pyOpenSSL >= 0.13
Requires:   python-setuptools
Recommends: python-miniupnpc
Conflicts:  re6st-node

%description

%build
make

%install
set $RPM_BUILD_ROOT
make install PREFIX=%_prefix MANDIR=%_mandir DESTDIR=$1
# Exclude man pages because they will be compressed.
find $1 -mindepth 1 -path \*%_mandir -prune -o \
  -name re6st\* -prune -printf /%%P\\n > INSTALLED

%clean
rm -rf "$RPM_BUILD_ROOT" INSTALLED

%files -f INSTALLED
%_mandir/*/*
/etc/NetworkManager

%post
if [ $1 -eq 1 ]; then
    /bin/systemctl enable re6stnet.service re6st-registry.service || :
fi >/dev/null 2>&1

%preun
if [ $1 -eq 0 ]; then
    /bin/systemctl --no-reload disable re6stnet.service re6st-registry.service || :
    /bin/systemctl stop re6stnet.service re6st-registry.service || :
fi >/dev/null 2>&1

%postun
/bin/systemctl daemon-reload >/dev/null 2>&1 || :
if [ $1 -ge 1 ] ; then
    # only try to restart the registry (doing same for re6stnet could be troublesome)
    /bin/systemctl try-restart re6st-registry.service >/dev/null 2>&1 || :
fi
