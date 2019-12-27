PACKAGE = $(shell dh_listpackages)
TMP = $(CURDIR)/debian/$(PACKAGE)

INIT = $(TMP)/etc/init.d

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
	make DESTDIR=$(TMP) PREFIX=/usr PYTHON=/usr/bin/python \
		install-noinit

override_dh_installinit:
	install -d $(INIT)
	sed 's/#NAME#/re6st-registry/; s,#DAEMON_DIR#,/usr/bin,' \
		<debian/init.d >$(INIT)/re6st-registry
	sed 's/#NAME#/re6stnet/; s,#DAEMON_DIR#,/usr/sbin,' \
		<debian/init.d >$(INIT)/re6stnet
	for x in $(INIT)/*; \
	do chmod +x $$x && dh_installinit --onlyscripts --name=$${x##*/}; \
	done
