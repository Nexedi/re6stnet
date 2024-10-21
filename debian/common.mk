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

override_dh_auto_test:

override_dh_auto_install:
	dh_auto_install
	make DESTDIR=$(TMP) PREFIX=/usr install
