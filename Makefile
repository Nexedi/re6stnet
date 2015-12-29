DESTDIR = /
PREFIX = /usr/local
MANDIR = $(PREFIX)/share/man
UNITDIR = /lib/systemd/system

MANPAGELIST := $(patsubst %,docs/%,re6st-conf.1 re6st-registry.1 re6stnet.8)
NM = /etc/NetworkManager/dispatcher.d/50re6stnet

all: $(MANPAGELIST)

%.1 %.8: %.rst
	rst2man $< $@

install: install-noinit
	for x in daemon/*.service; \
	do install -Dpm 0644 $$x $(DESTDIR)$(UNITDIR)/$${x##*/}; \
	done

install-noinit: install-man
	install -Dp daemon/network-manager $(DESTDIR)$(NM)
	set -e $(DESTDIR)$(PREFIX) /bin/re6stnet; [ -x $$1$$2 ] || \
	$(or $(PYTHON),python2) setup.py install \
		--prefix=$(PREFIX) --root=$(DESTDIR); \
	$(and $(PYTHON),sed -ri '1s:^#!\S+:#!$(PYTHON):' $(DESTDIR)$(NM);) \
	install -d $$1/sbin; mv $$1$$2 $$1/sbin
	install -Dpm 0644 daemon/README.conf $(DESTDIR)/etc/re6stnet/README
	install -Dpm 0644 daemon/logrotate.conf $(DESTDIR)/etc/logrotate.d/re6stnet

install-man: $(MANPAGELIST)
	set -e; for x in $^; \
	do install -Dpm 0644 $$x $(DESTDIR)$(MANDIR)/man$${x##*.}/$${x##*/}; \
	done

install-ifupdown:
	set -e; for a in up down; do \
	set $(DESTDIR)/etc/network/if-$$a.d/re6stnet; \
	install -d $${1%/*}; \
	printf '#!/bin/sh -e\n[ "$$METHOD" = NetworkManager -o "$$IFACE" = lo ] ||exec $(NM) "$$IFACE" %s\n' $$a >$$1; \
	chmod +x $$1; \
	done

clean:
	find -name '*.pyc' -delete
	rm -rf build dist re6stnet.egg-info $(MANPAGELIST)
