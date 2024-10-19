DESTDIR = /
# https://github.com/pypa/pip/issues/10978
PREFIX = /usr/local
MANDIR = $(PREFIX)/share/man
UNITDIR = $(PREFIX)/lib/systemd/system
PIP_INSTALL = python3 -m pip install

MANPAGELIST := $(patsubst %,docs/%,re6st-conf.1 re6st-registry.1 re6stnet.8)

all: $(MANPAGELIST)

%.1 %.8: %.rst
	rst2man $< $@

install: install-noinit
	for x in daemon/*.service; \
	do install -Dpm 0644 $$x $(DESTDIR)$(UNITDIR)/$${x##*/}; \
	done

install-noinit: install-man
	set -e $(DESTDIR)$(PREFIX) /bin/re6stnet; [ -x $$1$$2 ] || \
	{ [ "$(PREFIX)" = /usr/local ]; $(PIP_INSTALL) --root=$(DESTDIR) .; }; \
	install -d $$1/sbin; mv $$1$$2 $$1/sbin
	install -Dpm 0644 daemon/README.conf $(DESTDIR)/etc/re6stnet/README
	install -Dpm 0644 daemon/logrotate.conf $(DESTDIR)/etc/logrotate.d/re6stnet

install-man: $(MANPAGELIST)
	set -e; for x in $^; \
	do install -Dpm 0644 $$x $(DESTDIR)$(MANDIR)/man$${x##*.}/$${x##*/}; \
	done

clean:
	find -name __pycache__ -print0 |xargs -0 rm -rf dist $(MANPAGELIST)
