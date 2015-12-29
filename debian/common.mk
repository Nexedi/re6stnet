PACKAGE = $(shell dh_listpackages)
TMP = $(CURDIR)/debian/$(PACKAGE)

INIT = $(TMP)/etc/init.d

ifdef VERSION
define CHANGELOG
$(PACKAGE) ($(VERSION)) nexedi; urgency=low

 -- $(shell git var GIT_COMMITTER_IDENT |sed 's/[^>]*$$//')  $(shell date -R)
endef
export CHANGELOG

.PHONY: debian/changelog

debian/changelog:
	echo "$$CHANGELOG" >$@
endif

override_dh_install:
	make DESTDIR=$(TMP) PREFIX=/usr PYTHON=/usr/bin/python \
		install-noinit install-ifupdown

override_dh_installinit:
	install -d $(INIT)
	sed 's/#NAME#/re6st-registry/; s/#DEPENDS#//; s,#DAEMON_DIR#,/usr/bin,' \
		<debian/init.d >$(INIT)/re6st-registry
	sed 's/#NAME#/re6stnet/; s/#DEPENDS#/re6st-registry/; s,#DAEMON_DIR#,/usr/sbin,; /^case/i\
	cd $$CONFDIR; $$DAEMON @$$NAME.conf --test "main_interface != '\'lo\''" ||\
	case "$$1" in start) exit 0;; restart|force-reload) set stop;; esac\
	' <debian/init.d >$(INIT)/re6stnet
# First install *.service then update scripts.
	for x in $(INIT)/*; do set dh_installinit --name=$${x##*/} && \
		chmod +x $$x && "$$@" --noscripts && "$$@" --onlyscripts; \
	done
