# Turn off mangling shebangs as we have many scripts that we don't control
%undefine __brp_mangle_shebangs

%define _builddir %(pwd)
%define ver %(python2 re6st/version.py)
%define units re6stnet.service re6st-registry.service

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
Requires:   openvpn >= 2.4
Requires:   openvpn < 2.5
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
make install PREFIX=%_prefix MANDIR=%_mandir DESTDIR=$1 %{?_unitdir:UNITDIR=%{_unitdir}}
# Exclude man pages because they will be compressed.
find $1 -mindepth 1 -path \*%_mandir -prune -o \
  -name re6st\* -prune -printf /%%P\\n > INSTALLED

%clean
rm -rf "$RPM_BUILD_ROOT" INSTALLED

%files -f INSTALLED
%_mandir/*/*

%post
if [ $1 -eq 1 ]; then
    /bin/systemctl preset %{units} || :
fi >/dev/null 2>&1

%preun
if [ $1 -eq 0 ]; then
    /bin/systemctl --no-reload disable %{units} || :
    /bin/systemctl stop %{units} || :
fi >/dev/null 2>&1

%postun
/bin/systemctl daemon-reload >/dev/null 2>&1 || :
if [ $1 -ge 1 ]; then
    /bin/systemctl try-restart %{units} >/dev/null 2>&1 || :
fi
