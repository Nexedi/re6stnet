%define _builddir %(pwd)
%define ver %(python re6st/version.py)

Summary:   resilient, scalable, IPv6 network application
Name:      re6stnet
Version:   %(set %ver; echo ${1%%-*})
Release:   %(set %ver; echo ${1#*-})
License:   GPLv2+
Group:     Applications/Internet
BuildArch: noarch
Requires:  babeld = 1.5.1-nxd2
Requires:  iproute
Requires:  openssl
Requires:  openvpn
Requires:  python >= 2.7
Requires:  pyOpenSSL >= 0.13

%description

%build
for x in docs/*.rst
do rst2man $x ${x%%.rst}.1
done

%install
set $RPM_BUILD_ROOT /lib/systemd/system
python2.7 setup.py install --prefix %_prefix --root=$1
install -d $1%_sbindir $1%_mandir/man1 $1$2
install -Dpm 0644 docs/*.1 $1%_mandir/man1
install -Dpm 0644 daemon/*.service $1$2
install -Dp daemon/network-manager $1/etc/NetworkManager/dispatcher.d/50re6stnet
install -Dpm 0644 daemon/README.conf $1/etc/re6stnet/README.conf
install -Dpm 0644 daemon/logrotate.conf $1/etc/logrotate.d/re6stnet
mv $1%_bindir/re6stnet $1%_sbindir
find $1 -mindepth 1 -type d -name re6st\* -printf /%%P\\n > INSTALLED

%clean
find "$RPM_BUILD_ROOT" -delete
rm INSTALLED

%files -f INSTALLED
%doc README
%_bindir/*
%_sbindir/*
%_mandir/*/*
/lib/systemd/system/*
/etc/NetworkManager/dispatcher.d/50re6stnet
/etc/logrotate.d/re6stnet

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

%changelog
* Mon Dec 10 2012 Julien Muchembled <jm@nexedi.com>
- Initial package
