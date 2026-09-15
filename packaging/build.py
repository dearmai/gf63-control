#!/usr/bin/python3
"""Build binary/source RPMs and a portable install bundle from pinned sources."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
NAME = 'gf63-control-1.3.0'
BUILD = ROOT / '.build' / NAME / 'rpmbuild'


def main():
    for folder in ('SOURCES', 'SPECS', 'BUILD', 'BUILDROOT', 'RPMS', 'SRPMS'):
        (BUILD / folder).mkdir(parents=True, exist_ok=True)
    DIST.mkdir(exist_ok=True)
    files = [p for p in ROOT.iterdir() if p.suffix in ('.py', '.desktop', '.policy', '.svg') or p.name in ('Makefile', 'README.md', 'REUSE.md', 'AGENTS.md', 'LICENSE')]
    files += [p for folder in ('packaging', 'vendor') for p in (ROOT / folder).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts]
    source = BUILD / 'SOURCES' / (NAME + '.tar.gz')
    with tarfile.open(source, 'w:gz') as archive:
        for path in sorted(files):
            archive.add(path, arcname=NAME + '/' + str(path.relative_to(ROOT)))
    spec = ROOT / 'packaging/gf63-control.spec'
    subprocess.run(['rpmbuild', '-ba', '--define', '_topdir ' + str(BUILD), str(spec)], check=True)
    bundle = DIST / (NAME + '-rocky9-x86_64')
    bundle.mkdir(exist_ok=True)
    (bundle / 'rpms').mkdir(exist_ok=True)
    (bundle / 'sources').mkdir(exist_ok=True)
    for rpm in (BUILD / 'RPMS').rglob('*.rpm'):
        shutil.copy2(rpm, bundle / 'rpms')
    for rpm in (BUILD / 'SRPMS').glob('*.rpm'):
        shutil.copy2(rpm, bundle / 'sources')
    shutil.copy2(source, bundle / 'sources')
    shutil.copy2(ROOT / 'REUSE.md', bundle / 'README.md')
    shutil.copy2(ROOT / 'packaging/install.sh', bundle / 'install.sh')
    (bundle / 'install.sh').chmod(0o755)
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
