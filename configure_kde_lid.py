"""KDE PowerDevil lid policy, using fixed KConfig groups and readback."""
import os
import json
import shutil
import subprocess
import configure_mac
import desktop_env

BACKUP = configure_mac.BACKUP.with_name('kde-lid-backup.json')
PROFILES = ('AC', 'Battery', 'LowBattery')
MISSING = '__gf63_missing__'


def schema():
    version = os.environ.get('KDE_SESSION_VERSION')
    if version == '6' or (version != '5' and shutil.which('kwriteconfig6')):
        return '6', 'powerdevilrc', 'SuspendAndShutdown', 'LidAction'
    if version == '5' or shutil.which('kwriteconfig5'):
        return '5', 'powermanagementprofilesrc', 'HandleButtonEvents', 'lidAction'
    raise RuntimeError('KDE KConfig 도구(kwriteconfig5/6)를 찾을 수 없습니다.')


def command(tool, profile, *args):
    version, file, group, key = schema()
    return subprocess.run([tool + version, '--file', file, '--group', profile,
                           '--group', group, '--key', key, *args],
                          capture_output=True, text=True, check=True, timeout=8).stdout.strip()


def values():
    return {profile: command('kreadconfig', profile, '--default', MISSING) for profile in PROFILES}


def current():
    data = values()
    return 'true' if all(value == '0' for value in data.values()) else json.dumps(data, sort_keys=True)


def reload():
    # Remote KDE sessions may not run PowerDevil. Persist settings for its next
    # start; the system lid inhibitor remains effective without that daemon.
    running = desktop_env.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                               'org.freedesktop.DBus', 'NameHasOwner', '(s)',
                               ('org.kde.Solid.PowerManagement',))[0]
    if not running:
        return
    desktop_env.call('org.kde.Solid.PowerManagement', '/org/kde/Solid/PowerManagement',
                     'org.kde.Solid.PowerManagement', 'reparseConfiguration')


def write(raw):
    target = {profile: '0' for profile in PROFILES} if raw == 'true' else json.loads(raw)
    if set(target) != set(PROFILES):
        raise ValueError('KDE 덮개 프로필 값이 올바르지 않습니다.')
    for profile, value in target.items():
        if value == MISSING:
            command('kwriteconfig', profile, '--delete')
        else:
            command('kwriteconfig', profile, str(value))
    if values() != target:
        raise RuntimeError('KDE 덮개 설정 확인 실패')
    reload()


def configure(restore=False):
    if restore:
        if BACKUP.exists():
            old = json.loads(BACKUP.read_text())
            now = values()
            target = {profile: old[profile] if now[profile] == '0' else now[profile] for profile in PROFILES}
            write(json.dumps(target))
            BACKUP.unlink()
        return
    if not BACKUP.exists():
        configure_mac.save(values(), BACKUP)
    write('true')
