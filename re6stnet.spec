%define _builddir %(pwd)
%define ver %(python3 re6st/version.py)
%define units re6stnet.service re6st-registry.service

Summary:    resilient, scalable, IPv6 network application
Name:       re6stnet
Version:    %(set %ver; echo ${1%%-*})
Release:    %(set %ver; echo ${1#*-})
License:    GPLv2+
Group:      Applications/Internet
BuildArch:  noarch
Requires:   babeld = 1.12.1-nxd3
Requires:   iproute
Requires:   openssl
Requires:   openvpn >= 2.4
Requires:   openvpn < 2.5
Requires:   python >= 3.11
Requires:   pyOpenSSL >= 0.13
Requires:   python-setuptools
BuildRequires: python3-devel
# dependencies for compilation of python3
BuildRequires: libffi-devel
BuildRequires: (lzma-devel or liblzma-devel or xz-devel)
BuildRequires: zlib-devel
BuildRequires: (libbz2-devel or bzip2-devel)
Recommends: python-miniupnpc
Conflicts:  re6st-node

%description

%build
make
# Fix shebangs before Fedora's shebang mangling
%if 0%{?fedora}
%py3_shebang_fix $(grep -l -R -e "#\!.*python$")
%endif

%install
set $RPM_BUILD_ROOT
make install PREFIX=%_prefix MANDIR=%_mandir DESTDIR=$1 %{?_unitdir:UNITDIR=%{_unitdir}}
# Exclude man pages because they will be compressed.
find $1 -mindepth 1 -path \*%_mandir -prune -o \
  -name re6st\* -prune -printf /%%P\\n > INSTALLED
export QA_RPATHS=$(( 0x0001|0x0002|0x0020 ))

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
