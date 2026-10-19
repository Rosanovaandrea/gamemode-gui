#!/usr/bin/env bash
# Build the .deb and .rpm packages of the GameMode GUI.
#
# Usage:
#   packaging/build.sh
#
# Requirements for the .deb: dpkg-deb (package dpkg-dev/dpkg).
# Requirements for the .rpm: rpmbuild (package rpm-build). If it is not in the
# PATH, an alternative binary can be given with RPMBUILD and its config dir with
# RPMCONF, e.g.:
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
# Source tarball (used by the RPM)
# ---------------------------------------------------------------------------
SRCDIR="$WORK/$NAME-$VERSION"
mkdir -p "$SRCDIR/packaging"
install -m 644 "$ROOT"/{core.py,initializer.py,spec.py,configuration.py,LICENSE} "$SRCDIR/"
install -m 755 "$ROOT/main.py" "$SRCDIR/"
cp -r "$ROOT"/{data,i18n,sections,services,state,ui,vendor} "$SRCDIR/"
find "$SRCDIR" -name '__pycache__' -type d -prune -exec rm -rf {} +
install -m 644 "$HERE"/io.github.gamemodegui.GameModeGui.desktop \
    "$HERE"/io.github.gamemodegui.GameModeGui.svg \
    "$HERE"/gamemode-gui "$HERE"/gamemode-gui.spec "$SRCDIR/packaging/"
tar -C "$WORK" -czf "$WORK/$NAME-$VERSION.tar.gz" "$NAME-$VERSION"

# ---------------------------------------------------------------------------
# DEB
# ---------------------------------------------------------------------------
build_deb() {
    command -v dpkg-deb >/dev/null 2>&1 || {
        echo "!! dpkg-deb missing: skipping the .deb" >&2; return 0; }

    local tree="$WORK/deb"
    rm -rf "$tree"
    install -d "$tree/DEBIAN" \
        "$tree/usr/share/$NAME" \
        "$tree/usr/bin" \
        "$tree/usr/share/applications" \
        "$tree/usr/share/icons/hicolor/scalable/apps" \
        "$tree/usr/share/doc/$NAME"

    install -m 644 "$ROOT"/{core.py,initializer.py,spec.py,configuration.py} \
        "$tree/usr/share/$NAME/"
    install -m 755 "$ROOT/main.py" "$tree/usr/share/$NAME/"
    cp -r "$ROOT"/{data,i18n,sections,services,state,ui,vendor} \
        "$tree/usr/share/$NAME/"
    find "$tree/usr/share/$NAME" -name '__pycache__' -type d -prune -exec rm -rf {} +
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

# --- Configuration RESET (temporary behaviour) -------------------------------
# On install/upgrade, wipe the configuration managed by the GUI:
#   * /etc/gamemode.ini and its service files (.orig/.bak/.tmp/.session.json)
#   * the user preferences (~/.config/gamemode-gui/settings.json)
# So the new version always starts from a clean state.
rm -f /etc/gamemode.ini /etc/gamemode.ini.orig /etc/gamemode.ini.bak \
      /etc/gamemode.ini.tmp /etc/gamemode.ini.session.json
for home in /root /home/*; do
    [ -d "$home" ] || continue
    rm -f "$home/.config/gamemode-gui/settings.json"
done

# --- Desktop / icon cache ----------------------------------------------------
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
    echo "== DEB created: $DIST_DIR/${NAME}_${VERSION}-${RELEASE}_all.deb"
}

# ---------------------------------------------------------------------------
# RPM
# ---------------------------------------------------------------------------
build_rpm() {
    local top="$WORK/rpmbuild"
    mkdir -p "$top/BUILD" "$top/RPMS" "$top/SOURCES" "$top/SPECS" "$top/SRPMS" "$top/BUILDROOT"
    install -m 644 "$WORK/$NAME-$VERSION.tar.gz" "$top/SOURCES/"
    install -m 644 "$HERE/gamemode-gui.spec" "$top/SPECS/gamemode-gui.spec"
    # Align the spec Version/Release with those used for the tarball
    # (so the git tag, the tarball name and the RPM version match).
    sed -i "s/^Version:.*/Version:        $VERSION/" "$top/SPECS/gamemode-gui.spec"
    sed -i "s/^Release:.*/Release:        ${RELEASE}%{?dist}/" "$top/SPECS/gamemode-gui.spec"

    local cmd=()
    if command -v rpmbuild >/dev/null 2>&1; then
        cmd=(rpmbuild)
    elif [ -n "${RPMBUILD:-}" ]; then
        cmd=("$RPMBUILD")
        [ -n "${RPMCONF:-}" ] && cmd+=(--define "_rpmconfigdir $RPMCONF")
        # With a "portable" rpmbuild the brp/check-buildroot scripts are not in
        # /usr/lib/rpm: for a noarch Python package we skip them.
        cmd+=(--define "__os_install_post %{nil}" --define "__arch_install_post %{nil}")
    else
        echo "!! rpmbuild missing: skipping the .rpm (install rpm-build or set RPMBUILD/RPMCONF)" >&2
        return 0
    fi

    "${cmd[@]}" --define "_topdir $top" -bb "$top/SPECS/gamemode-gui.spec"
    find "$top/RPMS" -name '*.rpm' -exec cp {} "$DIST_DIR/" \;
    echo "== RPM created in: $DIST_DIR"
}

build_deb
build_rpm

echo
echo "Contents of $DIST_DIR:"
ls -l "$DIST_DIR"/*.deb "$DIST_DIR"/*.rpm 2>/dev/null || true
