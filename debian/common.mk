PACKAGE = $(shell dh_listpackages)
TMP = $(CURDIR)/debian/$(PACKAGE)

ifdef VERSION
define CHANGELOG
$(PACKAGE) ($(VERSION)) nexedi; urgency=low

 -- $(shell git log -1 --pretty='%cN <%cE>  %cD')
endef
export CHANGELOG

.PHONY: debian/changelog

debian/changelog:
	echo "$$CHANGELOG" >$@
endif

override_dh_install:
	make DESTDIR=$(TMP) PREFIX=/usr PYTHON=/usr/bin/python install

# BBB: compat < 10
override_dh_systemd_start:
	dh_systemd_start --restart-after-upgrade
