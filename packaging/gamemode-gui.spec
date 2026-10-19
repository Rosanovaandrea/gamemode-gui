Name:           gamemode-gui
Version:        1.0.0
Release:        1%{?dist}
Summary:        GUI for configuring Feral GameMode

License:        MIT
URL:            https://github.com/Rosanovaandrea/gamemode-gui
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       gamemode
Requires:       polkit
Recommends:     sudo

# Noarch package made only of Python scripts/data: no post-install processing
# (strip, bytecompile, mangle-shebang) is needed. Avoids brp dependencies and
# keeps the build reproducible even where the rpm helpers are incomplete.
%global __os_install_post %{nil}
%global __arch_install_post %{nil}

%description
A GTK4 + Libadwaita desktop application to manage the Feral GameMode
configuration file (gamemode.ini) in a visual, safe and atomic way.
It writes the administrator override in /etc/gamemode.ini, reading the
package-installed file as the base, and manages custom scripts, CPU core
pinning/parking and GPU optimisations.

%prep
%setup -q

%build
# No compilation: pure Python/GTK package.

%install
rm -rf %{buildroot}
install -d %{buildroot}%{_datadir}/%{name}
install -m 755 main.py %{buildroot}%{_datadir}/%{name}/main.py
cp -r gamemode_gui %{buildroot}%{_datadir}/%{name}/
find %{buildroot}%{_datadir}/%{name} -name '__pycache__' -type d -prune -exec rm -rf {} +

install -d %{buildroot}%{_bindir}
install -m 755 packaging/gamemode-gui %{buildroot}%{_bindir}/gamemode-gui

install -d %{buildroot}%{_datadir}/applications
install -m 644 packaging/io.github.gamemodegui.GameModeGui.desktop \
    %{buildroot}%{_datadir}/applications/io.github.gamemodegui.GameModeGui.desktop

install -d %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -m 644 packaging/io.github.gamemodegui.GameModeGui.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.gamemodegui.GameModeGui.svg

install -d %{buildroot}%{_datadir}/licenses/%{name}
install -m 644 LICENSE %{buildroot}%{_datadir}/licenses/%{name}/LICENSE

%post
# --- Configuration RESET (temporary behaviour) -------------------------------
# On install/upgrade, wipe the configuration managed by the GUI:
#   * /etc/gamemode.ini and its service files (.orig/.bak/.tmp/.session.json)
#   * the user preferences (~/.config/gamemode-gui/settings.json)
rm -f /etc/gamemode.ini /etc/gamemode.ini.orig /etc/gamemode.ini.bak \
      /etc/gamemode.ini.tmp /etc/gamemode.ini.session.json
for home in /root /home/*; do
    [ -d "$home" ] || continue
    rm -f "$home/.config/gamemode-gui/settings.json"
done

if [ -x %{_bindir}/update-desktop-database ]; then
    %{_bindir}/update-desktop-database -q %{_datadir}/applications || :
fi
if [ -x %{_bindir}/gtk-update-icon-cache ]; then
    %{_bindir}/gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor || :
fi

%postun
if [ -x %{_bindir}/update-desktop-database ]; then
    %{_bindir}/update-desktop-database -q %{_datadir}/applications || :
fi

%files
%{_datadir}/%{name}
%{_bindir}/gamemode-gui
%{_datadir}/applications/io.github.gamemodegui.GameModeGui.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.gamemodegui.GameModeGui.svg
%{_datadir}/licenses/%{name}/LICENSE

%changelog
* Thu Oct 01 2026 GameMode GUI contributors - 1.0.0-1
- Initial package
