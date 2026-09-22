# Working on GF63 Control

## Scope and architecture

This project targets MSI Thin GF63 12VE on two packaging tracks: Rocky Linux 9 x86_64
with XFCE/X11 (primary, best tested) and Debian/Ubuntu-family x86_64 via apt (secondary,
validated on HamoniKR 8 / Linux Mint 22 with Cinnamon).
The tested EC firmware is `16R8IMS1.108`; do not assume every GF63 firmware is compatible.
The application uses Python 3.9+, GTK 3 through PyGObject, standard sysfs interfaces,
XFCE shortcuts, PipeWire/WirePlumber, TuneD, and a firmware-matched msi-ec driver.

- `gf63_control.py`: non-root GTK application, worker queue, tray and OSD.
- `gf63_core.py`: bounded subprocess calls, read-only snapshots and action dispatch.
- `gf63_helper.py`: isolated Python root helper, fixed action/value allowlists.
- `local.gf63.control.policy`: authorization for the exact installed helper path.
- `configure_xfce.py`: per-user settings with backup and conditional restoration.
- `configure_cinnamon.py`: Cinnamon screenshot keybindings through GSettings, with a
  fixed accelerator allowlist and ownership-aware restore.
- `battery_limit.py`: standalone CLI retained for terminal users.
- `install_graphics.py`: read-only NVIDIA driver diagnosis; installation is handed
  to a terminal where the user runs sudo, never to the root helper.
- `packaging/`: binary/source RPM build and reusable installation bundle.
- `packaging/build_deb.py`, `packaging/deb/`, `packaging/install-deb.sh`: the apt track's
  package build, `DEBIAN` metadata/maintainer scripts and bundle installer.
- `vendor/msi-ec/`: upstream driver source, license and pinned commit provenance.

## Implementation boundaries

Keep the GUI unprivileged. Do not add arbitrary file paths, commands, shell evaluation,
or unchecked TuneD configuration to the root helper. Preserve its `python3 -I` shebang.
Validate every root action before mutation and read back the actual hardware setting.
Limit policy and helper changes to the documented hardware controls.

Never route package installation through the root helper or the polkit action.
`apt` runs arbitrary maintainer scripts as root, so driver installation opens a
terminal and the user authenticates there. Accept only `nvidia-driver-<digits>`
package names from `ubuntu-drivers devices`, never a name typed into the command.
Do not pass `-y`, do not reboot, and do not turn Secure Boot off or suggest it.

Use the driver's supported sysfs interface. Do not force firmware compatibility,
write raw EC addresses, disable Secure Boot, or invent unsupported fan/GPU controls.
The current EC `shift_mode` can report `unknown (192)`; CPU power presets use TuneD
instead of writing that undocumented state.

Do not read keyboard input globally for OSD. Observe actual device state and use
XFCE's named shortcuts. Preserve the screen lock boundary and suppress OSD while
the screen saver is active. Fn keys may be firmware-only; document unverified keys.

XFCE power manager owns brightness/keyboard-brightness keys even when its handling
option is disabled. Keep native brightness handling and observe changes for OSD.
Discover PulseAudio panel plugin IDs dynamically. Never assume `plugin-8` elsewhere.
Keep existing unrelated shortcuts and only restore values still owned by this app.
Cinnamon keybindings are GSettings string arrays. Write only accelerators from the module's
fixed list, refuse one another Cinnamon action already holds, and read the value back.

Keep GTK work on the main thread and blocking I/O on the worker. Bound subprocess
execution time. Show failures and unavailable controls rather than claiming success.
Use Korean UI text consistent with the existing application.

## Validation

Run `python3 -m unittest -v` from the repository root. These tests do not need root,
GUI access, or the physical device. Baseline: 19 tests, covering CLI, parsing,
device selection, allowed values, power presets and configuration injection rejection.
Add meaningful regression tests for hardware dispatch, rollback and parser changes.

For GTK changes, launch in a real XFCE session and inspect both the control panel
and OSD. Compile Python sources and validate desktop files. On hardware, snapshot
initial values, exercise a small reversible change, verify readback, and restore.
For power changes use `tuned-adm verify` and inspect actual Intel P-State/EPP/fan values.
Do not record audio/video or change network connectivity merely to test controls.
Document whether validation used physical Fn keys, synthetic keys, or direct actions.

Synthetic key tests can be swallowed by the screen saver. Check its state first;
do not bypass a locked session. Never report a passing key test from command exit
status alone: confirm actual hardware state changed.

## Packaging and release

Use `python3 packaging/build.py` on Rocky Linux 9 with `rpm-build` installed.
The build runs unit tests and emits GUI/CLI and DKMS RPMs, an SRPM, source archive,
an installation script, and SHA256 manifests under `dist/`.

On Debian/Ubuntu family use `python3 packaging/build_deb.py` with `dpkg-dev` installed;
`make check-env` and `make check-env-deb` gate each track, and `make install-deb` is the
apt-side counterpart of `make install`. The deb build runs the unit tests itself, since
there is no `%check` equivalent. Both tracks must install the identical layout, including
`/usr/libexec/gf63-control-helper`, which the polkit policy and `gf63_core.py` hardcode;
only the systemd unit path differs (`/usr/lib/systemd/system`). Normalize permissions in
the staged tree so the build user's umask cannot leak into the package.
Debian dependency names are mapped, not copied: `python3-gobject`/`gtk3` become
`python3-gi`/`gir1.2-gtk-3.0`, `polkit` becomes `polkitd | policykit-1` plus `pkexec`,
`kernel-devel` has no fixed name so the DKMS postinst checks `/lib/modules/$(uname -r)/build`.
Packages whose names drift across derivatives (`tuned`, `nimf-libhangul | ibus-hangul`, audio firmware,
appindicator, the XFCE set) are `Recommends`, not `Depends`, so one missing name on a
derivative cannot abort the whole transaction; the app must keep reporting those controls
as unavailable rather than failing.

Maintain the canonical `/usr/bin`, `/usr/share/gf63-control`, and `/usr/libexec` paths.
The old `/usr/local` installation is legacy; do not package personal home paths.
The installer runs as a desktop user and uses sudo only for system installation.
RPM scriptlets must not write another user's XFCE configuration.

When changing versions, update the spec's version/release and exact driver dependency,
the build script's archive naming, `%setup` source directory, and REUSE.md examples.
Mirror the same bump in `packaging/deb/*/DEBIAN/control`, `packaging/build_deb.py`
(`NAME`, `VERSION`, `DRIVER_VERSION`) and `packaging/REUSE-debian.md`, which all carry
literal versions the way the spec does.
Preserve upgrade/removal semantics and the pinned upstream commit/license.
Do not ship binaries compiled only for the build machine's kernel; DKMS builds on target.

Validate RPM digests and dependencies. Check install/file ownership/removal in an
isolated RPM root (use `--nodeps` for file verification there); separately validate
real dependency resolution and scriptlets on a suitable host. Avoid repeating DKMS
transactions unnecessarily, as they may regenerate initramfs.

Publish release assets from `dist/`, not as Git-tracked binaries. Never commit
`.build/`, caches, logs, credentials, local machine state or generated RPM databases.
Keep README.md and REUSE.md aligned with tested behavior. Preserve upstream GPL
notices separately from the project's MIT license. Check the exact source and bundle
contents before a public release.

## Known limits and improvement areas

- RPM targets Rocky 9 and the deb track targets the Debian/Ubuntu family; the deb track has
  seen far less use, and other distributions, architectures and EC versions are untested.
- Cinnamon support covers screen-lock detection, OSD suppression and the screenshot
  keybinding in `configure_cinnamon.py`. It has no xfconf, so `gf63-control-setup` registers
  autostart and skips other bindings there; Fn-key remapping and power-manager integration
  remain XFCE/KDE only. Extending `configure_cinnamon.py` to the rest of
  `org.cinnamon.desktop.keybindings` is the next step, mirroring `configure_kde.py`.
- Korean input supports IBus (`org.freedesktop.ibus.engine.hangul` `switch-keys`) and nimf
  (`org.nimf.engines.nimf-libhangul` `shortcuts-to-lang`/`shortcuts-to-sys`), detected per
  session and recorded in the backup. nimf's key table stops at F12, so F13-F20 switching is
  IBus only. Other input methods (Fcitx) are not detected and are left untouched. Physical
  key presses on nimf are unverified; only settings read/write/restore were checked.
- Full reboot verification and all physical Fn combinations remain unverified.
- Fan RPM curves and GPU power limits are not exposed by the chosen driver.
- The NVIDIA section is apt-only and reports itself unavailable on the RPM track.
  It was verified on this machine for status and command building; the terminal
  install path was exercised only up to opening the terminal.
- A different power manager may replace the selected TuneD profile.
- State polling and Gtk.StatusIcon are pragmatic XFCE choices; improve them without
  adding duplicate key handling or blocking the UI.
- Improve power-action progress/errors in the active tab, unsupported-CPU UI state,
  installer migration, and rollback tests before broadening hardware support.
