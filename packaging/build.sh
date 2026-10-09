#!/usr/bin/env bash
# Costruisce il pacchetto .deb e .rpm della GUI di GameMode.
#
# Uso:
#   packaging/build.sh
#
# Requisiti per il .deb: dpkg-deb (pacchetto dpkg-dev/dpkg).
# Requisiti per l'.rpm: rpmbuild (pacchetto rpm-build). Se non è nel PATH, si
# può indicare un binario alternativo con RPMBUILD e la sua config dir con
# RPMCONF, es.:
#   RPMBUILD=/path/usr/bin/rpmbuild RPMCONF=/path/rpmconf packaging/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
NAME="gamemode-gui"
VERSION="${VERSION:-1.0.0}"
RELEASE="${RELEASE:-1}"
DIST_DIR="$ROOT/dist"
WORK="$DIST_DIR/_work"

rm -rf "$WORK"
mkdir -p "$WORK" "$DIST_DIR"

# ---------------------------------------------------------------------------
# Tarball sorgente (usato dall'RPM)
# ---------------------------------------------------------------------------
SRCDIR="$WORK/$NAME-$VERSION"
mkdir -p "$SRCDIR/locale" "$SRCDIR/packaging"
install -m 644 "$ROOT"/{core.py,ui.py,widgets.py,privileged.py,fileops.py,options.json,presentation.json,style.css,LICENSE} "$SRCDIR/"
install -m 755 "$ROOT/main.py" "$SRCDIR/main.py"
install -m 644 "$ROOT/locale/it.xml" "$ROOT/locale/en.xml" "$SRCDIR/locale/"
install -m 644 "$HERE"/io.github.gamemodegui.GameModeGui.desktop \
    "$HERE"/io.github.gamemodegui.GameModeGui.svg \
    "$HERE"/gamemode-gui "$HERE"/gamemode-gui.spec "$SRCDIR/packaging/"
tar -C "$WORK" -czf "$WORK/$NAME-$VERSION.tar.gz" "$NAME-$VERSION"

# ---------------------------------------------------------------------------
# DEB
# ---------------------------------------------------------------------------
build_deb() {
    command -v dpkg-deb >/dev/null 2>&1 || {
        echo "!! dpkg-deb assente: salto il .deb" >&2; return 0; }

    local tree="$WORK/deb"
    rm -rf "$tree"
    install -d "$tree/DEBIAN" \
        "$tree/usr/share/$NAME/locale" \
        "$tree/usr/bin" \
        "$tree/usr/share/applications" \
        "$tree/usr/share/icons/hicolor/scalable/apps" \
        "$tree/usr/share/doc/$NAME"

    install -m 644 "$ROOT"/core.py "$ROOT"/ui.py "$ROOT"/widgets.py \
        "$ROOT"/privileged.py "$ROOT"/fileops.py "$ROOT"/options.json \
        "$ROOT"/presentation.json "$ROOT"/style.css "$tree/usr/share/$NAME/"
    install -m 755 "$ROOT/main.py" "$tree/usr/share/$NAME/main.py"
    install -m 644 "$ROOT/locale/it.xml" "$ROOT/locale/en.xml" \
        "$tree/usr/share/$NAME/locale/"
    install -m 755 "$HERE/gamemode-gui" "$tree/usr/bin/gamemode-gui"
    install -m 644 "$HERE/io.github.gamemodegui.GameModeGui.desktop" \
        "$tree/usr/share/applications/io.github.gamemodegui.GameModeGui.desktop"
    install -m 644 "$HERE/io.github.gamemodegui.GameModeGui.svg" \
        "$tree/usr/share/icons/hicolor/scalable/apps/io.github.gamemodegui.GameModeGui.svg"
    install -m 644 "$ROOT/LICENSE" "$tree/usr/share/doc/$NAME/copyright"

    local size
    size=$(du -sk "$tree/usr" | cut -f1)

    cat > "$tree/DEBIAN/control" <<EOF
Package: $NAME
Version: $VERSION-$RELEASE
Section: utils
Priority: optional
Architecture: all
Maintainer: GameMode GUI contributors <noreply@example.com>
Installed-Size: $size
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gamemode-daemon | gamemode, pkexec | policykit-1
Recommends: sudo
Homepage: https://github.com/Rosanovaandrea/gamemode-gui
Description: GUI to configure Feral GameMode
 A GTK4 + Libadwaita desktop application to manage gamemode.ini in a
 visual, safe and atomic way.
EOF

    cat > "$tree/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e

# --- RESET configurazione (comportamento temporaneo) -------------------------
# All'installazione/aggiornamento azzera la configurazione gestita dalla GUI:
#   * /etc/gamemode.ini e i suoi file di servizio (.orig/.bak/.tmp/.session.json)
#   * le preferenze utente (~/.config/gamemode-gui/settings.json)
# Così la nuova versione riparte sempre da uno stato pulito.
rm -f /etc/gamemode.ini /etc/gamemode.ini.orig /etc/gamemode.ini.bak \
      /etc/gamemode.ini.tmp /etc/gamemode.ini.session.json
for home in /root /home/*; do
    [ -d "$home" ] || continue
    rm -f "$home/.config/gamemode-gui/settings.json"
done

# --- Cache desktop / icone ---------------------------------------------------
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF

    cat > "$tree/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF

    chmod 755 "$tree/DEBIAN/postinst" "$tree/DEBIAN/postrm"
    dpkg-deb --root-owner-group --build "$tree" \
        "$DIST_DIR/${NAME}_${VERSION}-${RELEASE}_all.deb"
    echo "== DEB creato: $DIST_DIR/${NAME}_${VERSION}-${RELEASE}_all.deb"
}

# ---------------------------------------------------------------------------
# RPM
# ---------------------------------------------------------------------------
build_rpm() {
    local top="$WORK/rpmbuild"
    mkdir -p "$top/BUILD" "$top/RPMS" "$top/SOURCES" "$top/SPECS" "$top/SRPMS" "$top/BUILDROOT"
    install -m 644 "$WORK/$NAME-$VERSION.tar.gz" "$top/SOURCES/"
    install -m 644 "$HERE/gamemode-gui.spec" "$top/SPECS/gamemode-gui.spec"
    # Allinea la Version/Release dello spec a quelle usate per il tarball
    # (così il tag git, il nome del tarball e la versione RPM coincidono).
    sed -i "s/^Version:.*/Version:        $VERSION/" "$top/SPECS/gamemode-gui.spec"
    sed -i "s/^Release:.*/Release:        ${RELEASE}%{?dist}/" "$top/SPECS/gamemode-gui.spec"

    local cmd=()
    if command -v rpmbuild >/dev/null 2>&1; then
        cmd=(rpmbuild)
    elif [ -n "${RPMBUILD:-}" ]; then
        cmd=("$RPMBUILD")
        [ -n "${RPMCONF:-}" ] && cmd+=(--define "_rpmconfigdir $RPMCONF")
        # Con un rpmbuild "portatile" gli script brp/check-buildroot non sono
        # in /usr/lib/rpm: per un pacchetto noarch Python li saltiamo.
        cmd+=(--define "__os_install_post %{nil}" --define "__arch_install_post %{nil}")
    else
        echo "!! rpmbuild assente: salto l'.rpm (installa rpm-build o imposta RPMBUILD/RPMCONF)" >&2
        return 0
    fi

    "${cmd[@]}" --define "_topdir $top" -bb "$top/SPECS/gamemode-gui.spec"
    find "$top/RPMS" -name '*.rpm' -exec cp {} "$DIST_DIR/" \;
    echo "== RPM creato in: $DIST_DIR"
}

build_deb
build_rpm

echo
echo "Contenuto di $DIST_DIR:"
ls -l "$DIST_DIR"/*.deb "$DIST_DIR"/*.rpm 2>/dev/null || true
