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
	make DESTDIR=$(TMP) PREFIX=/usr install

# BBB: compat < 10 ; https://bugs.debian.org/879727
override_dh_systemd_start:
	dh_systemd_start --restart-after-upgrade
	sed -i 's/_dh_action=try-restart/_dh_action=restart; for x in re6stnet re6st-registry; do systemctl is-enabled --quiet $$x.service || &; done/' debian/$(PACKAGE).postinst.debhelper
