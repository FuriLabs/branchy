PREFIX ?= /usr
LIBDIR = $(PREFIX)/lib
BINDIR = $(PREFIX)/bin
SHAREDIR = $(PREFIX)/share

INSTALL_DIR = $(LIBDIR)/branchy
DESKTOP_DIR = $(SHAREDIR)/applications
ICON_DIR = $(SHAREDIR)/icons/hicolor/scalable/apps

.PHONY: all install uninstall

all:
	@echo "Run 'make install' to install the files."

install:
	install -d $(DESTDIR)$(INSTALL_DIR)
	install -d $(DESTDIR)$(BINDIR)
	install -d $(DESTDIR)$(DESKTOP_DIR)
	install -d $(DESTDIR)$(ICON_DIR)

	cp -r branchy $(DESTDIR)$(INSTALL_DIR)/

	install -m 755 main.py $(DESTDIR)$(INSTALL_DIR)/

	install -m 644 data/io.furios.Branchy.desktop $(DESTDIR)$(DESKTOP_DIR)/
	install -m 644 data/io.furios.Branchy.svg $(DESTDIR)$(ICON_DIR)/

	ln -sf ../lib/branchy/main.py $(DESTDIR)$(BINDIR)/io.furios.Branchy

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/io.furios.Branchy

	rm -rf $(DESTDIR)$(INSTALL_DIR)
	rm -f $(DESTDIR)$(DESKTOP_DIR)/io.furios.Branchy.desktop
	rm -f $(DESTDIR)$(ICON_DIR)/io.furios.Branchy.svg
