Name:           gf63-control
Version:        1.4.0
Release:        1%{?dist}
Summary:        MSI GF63 GTK control panel, function keys and OSD
License:        MIT AND OFL-1.1
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3, systemd-rpm-macros
Requires:       python3, python3-gobject, gtk3, polkit, fontconfig
Recommends:     xfce4-settings, xfce4-power-manager, xfce4-panel, xfce4-notifyd
Recommends:     libappindicator-gtk3, flatpak
Requires:       xorg-x11-server-utils, ibus, ibus-hangul
Requires:       xdotool, xinput, wireplumber, pipewire, pipewire-pulseaudio
Requires:       alsa-sof-firmware, alsa-ucm, systemd, tuned
Requires:       msi-ec-dkms = 0.13-1%{?dist}

%description
Control battery charge thresholds, display and keyboard brightness, audio,
touchpads, webcam and Cooler Boost on supported MSI firmware. Includes
the battery-limit CLI and a per-user XFCE setup/restore utility.

%package -n msi-ec-dkms
Version:        0.13
Summary:        MSI embedded controller driver sources for DKMS
License:        GPL-2.0-or-later
Requires:       dkms, gcc, make, kernel-devel, kmod
Requires(post): dkms, kmod
Requires(preun): dkms

%description -n msi-ec-dkms
Pinned upstream msi-ec driver sources. Firmware compatibility is detected
by the driver. No firmware override or raw EC writes are configured.

%prep
%setup -q -n gf63-control-1.4.0

%build

%install
install -d %{buildroot}%{_bindir} %{buildroot}%{_datadir}/gf63-control %{buildroot}%{_libexecdir}
install -m 0755 packaging/gf63-control packaging/gf63-control-setup packaging/gf63-mac-shortcut %{buildroot}%{_bindir}/
install -m 0755 battery_limit.py %{buildroot}%{_bindir}/battery-limit
install -m 0644 gf63_control.py gf63_core.py configure_xfce.py configure_keyboard.py configure_lid.py configure_mac.py mac_shortcut.py desktop_env.py configure_kde.py configure_kde_lid.py configure_fonts.py configure_cinnamon.py install_fonts.py install_programs.py install_graphics.py gf63-control-autostart.desktop %{buildroot}%{_datadir}/gf63-control/
install -d %{buildroot}%{_datadir}/gf63-control/vendor
install -m 0644 gf63-control.svg %{buildroot}%{_datadir}/gf63-control/
cp -a vendor/fonts %{buildroot}%{_datadir}/gf63-control/vendor/
install -m 0755 gf63_lid.py %{buildroot}%{_libexecdir}/gf63-lid
install -Dm 0644 packaging/gf63-lid.service %{buildroot}%{_unitdir}/gf63-lid.service
install -m 0755 gf63_helper.py %{buildroot}%{_libexecdir}/gf63-control-helper
install -Dm 0644 gf63-control.desktop %{buildroot}%{_datadir}/applications/gf63-control.desktop
install -Dm 0644 local.gf63.control.policy %{buildroot}%{_datadir}/polkit-1/actions/local.gf63.control.policy
install -d %{buildroot}/usr/src/msi_ec-0.13
install -m 0644 vendor/msi-ec/{msi-ec.c,ec_memory_configuration.h,Makefile,dkms.conf,UPSTREAM} %{buildroot}/usr/src/msi_ec-0.13/
install -d %{buildroot}/usr/lib/modules-load.d
echo msi-ec > %{buildroot}/usr/lib/modules-load.d/gf63-msi-ec.conf

%check
python3 -m unittest -v

%post
%systemd_post gf63-lid.service

%preun
%systemd_preun gf63-lid.service

%postun
%systemd_postun_with_restart gf63-lid.service

%post -n msi-ec-dkms
if ! dkms status -m msi_ec -v 0.13 | grep -q .; then
    dkms add -m msi_ec -v 0.13 || echo 'msi-ec: DKMS registration failed' >&2
fi
if test -d /lib/modules/"$(uname -r)"/build; then
    dkms install -m msi_ec -v 0.13 -k "$(uname -r)" || echo 'msi-ec: build failed; inspect dkms status and make.log' >&2
else
    echo 'msi-ec: install kernel-devel for the running kernel, then run dkms install msi_ec/0.13' >&2
fi
modprobe msi-ec || echo 'msi-ec: module load failed; check firmware support and Secure Boot' >&2
exit 0

%preun -n msi-ec-dkms
if [ "$1" -eq 0 ]; then
    dkms remove -m msi_ec -v 0.13 --all || :
fi

%files
%license LICENSE vendor/fonts/pretendard/LICENSE.txt vendor/fonts/d2coding/OFL.txt
%doc README.md REUSE.md AGENTS.md
%{_bindir}/gf63-control
%{_bindir}/gf63-control-setup
%{_bindir}/gf63-mac-shortcut
%{_bindir}/battery-limit
%{_datadir}/gf63-control/
%{_libexecdir}/gf63-control-helper
%{_libexecdir}/gf63-lid
%{_unitdir}/gf63-lid.service
%{_datadir}/applications/gf63-control.desktop
%{_datadir}/polkit-1/actions/local.gf63.control.policy

%files -n msi-ec-dkms
%license vendor/msi-ec/LICENSE
%doc vendor/msi-ec/UPSTREAM
/usr/src/msi_ec-0.13/
/usr/lib/modules-load.d/gf63-msi-ec.conf

%changelog
* Tue Sep 22 2026 GF63 Control contributors - 1.4.0-1
- Support nimf alongside IBus for Korean switching.
- Add NVIDIA driver status and guided install to the program tab.
- Add the Cinnamon screenshot shortcut control.

* Wed Sep 09 2026 GF63 Control contributors - 1.3.0-1
- Add KDE Plasma X11 shortcuts, screen-lock integration and PowerDevil lid handling.

* Wed Sep 09 2026 GF63 Control contributors - 1.2.0-1
- Add optional Mac-style XFCE shortcuts with terminal-aware dispatch and restore.

* Wed Sep 09 2026 GF63 Control contributors - 1.1.0-1
- Add persistent closed-lid operation with internal display blanking.

* Wed Sep 09 2026 GF63 Control contributors - 1.0.0-1
- Package GUI, CLI, per-user setup and pinned DKMS source.
