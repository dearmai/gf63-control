#!/usr/bin/python3
"""Build Debian packages and a portable install bundle from the same pinned sources."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
NAME = 'gf63-control-1.3.0'
VERSION = '1.3.0-1'
DRIVER_VERSION = '0.13'
BUILD = ROOT / '.build' / NAME / 'deb'

SHARED = ['gf63_control.py', 'gf63_core.py', 'configure_xfce.py', 'configure_keyboard.py',
          'configure_lid.py', 'configure_mac.py', 'mac_shortcut.py', 'desktop_env.py',
          'configure_kde.py', 'configure_kde_lid.py', 'configure_fonts.py', 'install_fonts.py',
          'install_programs.py', 'install_graphics.py', 'configure_cinnamon.py', 'gf63-control-autostart.desktop', 'gf63-control.svg']
DRIVER_SOURCES = ['msi-ec.c', 'ec_memory_configuration.h', 'Makefile', 'dkms.conf', 'UPSTREAM']


def copy(source, target, mode):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(mode)


def stage_app(root):
    for name in ('gf63-control', 'gf63-control-setup', 'gf63-mac-shortcut'):
        copy(ROOT / 'packaging' / name, root / 'usr/bin' / name, 0o755)
    copy(ROOT / 'battery_limit.py', root / 'usr/bin/battery-limit', 0o755)
    for name in SHARED:
        copy(ROOT / name, root / 'usr/share/gf63-control' / name, 0o644)
    shutil.copytree(ROOT / 'vendor/fonts', root / 'usr/share/gf63-control/vendor/fonts')
    copy(ROOT / 'gf63_helper.py', root / 'usr/libexec/gf63-control-helper', 0o755)
    copy(ROOT / 'gf63_lid.py', root / 'usr/libexec/gf63-lid', 0o755)
    copy(ROOT / 'packaging/gf63-lid.service', root / 'usr/lib/systemd/system/gf63-lid.service', 0o644)
    copy(ROOT / 'gf63-control.desktop', root / 'usr/share/applications/gf63-control.desktop', 0o644)
    copy(ROOT / 'local.gf63.control.policy',
         root / 'usr/share/polkit-1/actions/local.gf63.control.policy', 0o644)
    for name in ('README.md', 'REUSE.md', 'AGENTS.md'):
        copy(ROOT / name, root / 'usr/share/doc/gf63-control' / name, 0o644)
    licenses = [('MIT (gf63-control)', ROOT / 'LICENSE'),
                ('OFL-1.1 (Pretendard)', ROOT / 'vendor/fonts/pretendard/LICENSE.txt'),
                ('OFL-1.1 (D2Coding)', ROOT / 'vendor/fonts/d2coding/OFL.txt')]
    text = '\n\n'.join('=== ' + title + ' ===\n\n' + path.read_text() for title, path in licenses)
    target = root / 'usr/share/doc/gf63-control/copyright'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    target.chmod(0o644)


def stage_driver(root):
    for name in DRIVER_SOURCES:
        copy(ROOT / 'vendor/msi-ec' / name, root / ('usr/src/msi_ec-' + DRIVER_VERSION) / name, 0o644)
    copy(ROOT / 'vendor/msi-ec/LICENSE', root / 'usr/share/doc/msi-ec-dkms/copyright', 0o644)
    target = root / 'usr/lib/modules-load.d/gf63-msi-ec.conf'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('msi-ec\n')
    target.chmod(0o644)


def build_package(package, stage):
    root = BUILD / package
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    stage(root)
    for name in ('control', 'postinst', 'prerm'):
        source = ROOT / 'packaging/deb' / package / 'DEBIAN' / name
        if source.exists():
            copy(source, root / 'DEBIAN' / name, 0o644 if name == 'control' else 0o755)
    # The build user's umask must not leak into package permissions.
    for path in root.rglob('*'):
        path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o100 else 0o644)
    root.chmod(0o755)
    output = BUILD / (package + '_' + (VERSION if package == 'gf63-control' else DRIVER_VERSION + '-1') + '_all.deb')
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(root), str(output)], check=True)
    return output


def main():
    subprocess.run(['python3', '-m', 'unittest'], cwd=ROOT, check=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(exist_ok=True)
    packages = [build_package('gf63-control', stage_app), build_package('msi-ec-dkms', stage_driver)]
    files = [p for p in ROOT.iterdir() if p.suffix in ('.py', '.desktop', '.policy', '.svg')
             or p.name in ('Makefile', 'README.md', 'REUSE.md', 'AGENTS.md', 'LICENSE')]
    files += [p for folder in ('packaging', 'vendor') for p in (ROOT / folder).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts]
    source = BUILD / (NAME + '.tar.gz')
    with tarfile.open(source, 'w:gz') as archive:
        for path in sorted(files):
            archive.add(path, arcname=NAME + '/' + str(path.relative_to(ROOT)))
    bundle = DIST / (NAME + '-debian-x86_64')
    shutil.rmtree(bundle, ignore_errors=True)
    (bundle / 'debs').mkdir(parents=True)
    (bundle / 'sources').mkdir()
    for package in packages:
        shutil.copy2(package, bundle / 'debs')
    shutil.copy2(source, bundle / 'sources')
    shutil.copy2(ROOT / 'packaging/REUSE-debian.md', bundle / 'README.md')
    copy(ROOT / 'packaging/install-deb.sh', bundle / 'install.sh', 0o755)
    checksums = []
    for path in sorted(bundle.rglob('*')):
        if path.is_file() and path.name != 'SHA256SUMS':
            checksums.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(bundle)))
    (bundle / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n')
    output = DIST / (bundle.name + '.tar.gz')
    with tarfile.open(output, 'w:gz') as archive:
        archive.add(bundle, arcname=bundle.name)
    Path(str(output) + '.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest() + '  ' + output.name + '\n')
    print('Bundle:', output)


if __name__ == '__main__':
    main()
