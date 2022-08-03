%global __os_install_post %(echo '%{__os_install_post}' |grep -v brp-python-bytecompile)

%define units re6stnet.service re6st-registry.service

Summary:    resilient, scalable, IPv6 network application
Name:       re6st-node
Version:    0.581+slapos1.gf9dedb5db
Release:    1
License:    GPLv2+
Group:      Applications/Internet
AutoReqProv: no
BuildRequires: gcc-c++, make, python, iproute, python3-devel
#!BuildIgnore: rpmlint-Factory
Source: %{name}_%{version}.tar.gz
Requires:   iproute
Conflicts:  re6stnet

%description
%prep
%setup -q

%build
make
# Fix shebangs before Fedora's shebang mangling
pathfix.py -i %{__python3} -p -n $(grep -l -R -e "#\!.*python$")

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
find /opt/re6st -type f -name '*.py[co]' -delete

%postun
/bin/systemctl daemon-reload >/dev/null 2>&1 || :
if [ $1 -ge 1 ]; then
    /bin/systemctl try-restart %{units} >/dev/null 2>&1 || :
fi
