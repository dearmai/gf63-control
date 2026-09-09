"""Delegate this user's lid handling to logind, with conditional restoration."""
import desktop_env
import json
import os
from pathlib import Path
import subprocess

BACKUP = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'gf63-control/lid-backup.json'
PROP = '/xfce4-power-manager/logind-handle-lid-switch'


def query(*args):
    return subprocess.run(['xfconf-query', '-c', 'xfce4-power-manager', *args],
                          capture_output=True, text=True, timeout=8, check=True).stdout.strip()


def backup_path():
    if desktop_env.kind() == 'kde':
        import configure_kde_lid
        return configure_kde_lid.BACKUP
    return BACKUP


def current():
    if desktop_env.kind() == 'kde':
        import configure_kde_lid
        return configure_kde_lid.current()
    # Listing distinguishes an absent property from a broken session bus.
    props = query('-l').splitlines()
    return query('-p', PROP) if PROP in props else None


def write(value):
    if desktop_env.kind() == 'kde':
        import configure_kde_lid
        return configure_kde_lid.write(value)
    old = current()
    if value is None:
        if old is not None:
            query('-p', PROP, '-r')
    elif old is None:
        query('-p', PROP, '-n', '-t', 'bool', '-s', value)
    else:
        query('-p', PROP, '-s', value)
    if current() != value:
        raise RuntimeError('덮개 XFCE 설정을 확인하지 못했습니다.')


def configure(restore=False):
    if desktop_env.kind() == 'kde':
        import configure_kde_lid
        return configure_kde_lid.configure(restore=restore)
    if restore:
        if BACKUP.exists():
            old = json.loads(BACKUP.read_text())['old']
            if current() == 'true':
                write(old)
            BACKUP.unlink()
        return
    old = current()
    if not BACKUP.exists():
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_text(json.dumps({'old': old}))
    write('true')
