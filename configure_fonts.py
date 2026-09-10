"""Opt-in KDE/GNOME/Konsole fonts with per-user backup and conditional rollback."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

import configure_mac
import desktop_env

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
DATA = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
BACKUP = CONFIG / 'gf63-control/kde-fonts.json'
GNOME_BACKUP = CONFIG / 'gf63-control/gnome-fonts.json'
PROFILE_NAME = 'GF63-D2Coding.profile'
MISSING = '__gf63_font_missing__'
AUTOSTART = CONFIG / 'autostart/gf63-control-fonts.desktop'
AUTOSTART_TEXT = '''[Desktop Entry]
Type=Application
Name=GF63 Control Fonts
Name[ko]=GF63 글꼴 설정
Exec=/usr/bin/python3 /usr/share/gf63-control/configure_fonts.py --login
TryExec=/usr/bin/python3
OnlyShowIn=GNOME;
Terminal=false
X-GNOME-Autostart-enabled=true
'''



def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True, timeout=8).stdout.rstrip('\n')


def environment():
    # Font support does not imply support for GNOME hardware shortcuts or OSD.
    names = (os.environ.get('XDG_CURRENT_DESKTOP', '') + ':' +
             os.environ.get('XDG_SESSION_DESKTOP', '')).lower().split(':')
    return 'gnome' if any(name in ('gnome', 'gnome-classic') for name in names) else desktop_env.kind()


GNOME_KEYS = (
    ('org.gnome.desktop.interface', 'font-name'),
    ('org.gnome.desktop.interface', 'document-font-name'),
    ('org.gnome.desktop.interface', 'monospace-font-name'),
    ('org.gnome.desktop.wm.preferences', 'titlebar-font'),
)
# Isolate GSettings synchronization in a bounded subprocess. A missing schema
# must be reported before Gio.Settings.new_full can abort the process.
GNOME_SCRIPT = """
import json, sys, gi
gi.require_version('Pango', '1.0')
from gi.repository import Gio, Pango
operation, schema, key, value = json.loads(sys.argv[1])
source = Gio.SettingsSchemaSource.get_default()
definition = source.lookup(schema, True) if source else None
if definition is None or not definition.has_key(key):
    raise RuntimeError('GNOME 글꼴 설정 스키마가 없습니다: ' + schema + '/' + key)
settings = Gio.Settings.new_full(definition, None, None)
if operation == 'write':
    if not settings.is_writable(key):
        raise RuntimeError('관리자가 잠근 글꼴 설정입니다: ' + key)
    if value is None:
        settings.reset(key)
    elif not settings.set_string(key, value):
        raise RuntimeError('GNOME 글꼴 저장 실패: ' + key)
    Gio.Settings.sync()
user = settings.get_user_value(key)
result = dict(old=user.unpack() if user is not None else None,
              effective=settings.get_string(key), writable=settings.is_writable(key))
if operation == 'plan':
    description = Pango.FontDescription.from_string(result['effective'])
    description.set_family(value)
    result['installed'] = description.to_string()
print(json.dumps(result))
"""


def gnome_access(operation, item, value=None):
    if (item['schema'], item['key']) not in GNOME_KEYS:
        raise ValueError('지원하지 않는 GNOME 글꼴 설정입니다.')
    try:
        return json.loads(run(sys.executable, '-I', '-c', GNOME_SCRIPT,
                              json.dumps([operation, item['schema'], item['key'], value])))
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or '').strip().splitlines()
        raise RuntimeError(detail[-1] if detail else 'GNOME 글꼴 설정 도구 실행 실패') from exc


def gnome_plan():
    pretendard = required_fonts()
    state = []
    for schema, key in GNOME_KEYS:
        item = dict(kind='gnome', schema=schema, key=key)
        values = gnome_access('plan', item, 'D2Coding' if key == 'monospace-font-name' else pretendard)
        if not values['writable']:
            raise RuntimeError('관리자가 잠근 글꼴 설정입니다: ' + key)
        item.update(old=values['old'], installed=values['installed'])
        state.append(item)
    return state


def version():
    requested = os.environ.get('KDE_SESSION_VERSION')
    for value in ([requested] if requested in ('5', '6') else ['6', '5']):
        if all(shutil.which(tool + value) for tool in ('kreadconfig', 'kwriteconfig')):
            return value
    raise RuntimeError('KDE KConfig 도구(kreadconfig/kwriteconfig 5 또는 6)가 필요합니다.')


def read_key(file, group, key):
    value = run('kreadconfig' + version(), '--file', str(file), '--group', group,
                '--key', key, '--default', MISSING)
    return None if value == MISSING else value


def write_key(file, group, key, value):
    Path(file).parent.mkdir(parents=True, exist_ok=True)
    run('kwriteconfig' + version(), '--file', str(file), '--group', group,
        '--key', key, *(['--delete'] if value is None else [value]))


def families():
    # fc-match silently substitutes missing fonts; require an installed family.
    return {name.strip() for line in run('fc-list', '--format=%{family}\n').splitlines()
            for name in line.split(',')}


def font(family, previous=None, size=10):
    parts = (previous or f'Sans,{size},-1,5,50,0,0,0,0,0').split(',')
    if len(parts) < 10:
        raise RuntimeError('기존 글꼴 설정 형식을 읽을 수 없습니다.')
    # A previous family's named style may not exist in the new family.
    return ','.join([family] + parts[1:10])


def read(item):
    if item['kind'] == 'gnome':
        return gnome_access('read', item)['old']
    if item['kind'] == 'profile':
        path = DATA / 'konsole' / PROFILE_NAME
        return path.read_text() if path.exists() else None
    return read_key(CONFIG / item['file'], item['group'], item['key'])


def write(item, value):
    if item['kind'] == 'gnome':
        gnome_access('write', item, value)
    elif item['kind'] == 'profile':
        path = DATA / 'konsole' / PROFILE_NAME
        if value is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=path.parent)
            try:
                with os.fdopen(fd, 'w') as output:
                    output.write(value)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    else:
        write_key(CONFIG / item['file'], item['group'], item['key'], value)
    if read(item) != value:
        raise RuntimeError('글꼴 설정 확인 실패')


def required_fonts():
    installed = families()
    pretendard = next((name for name in ('Pretendard', 'Pretendard Variable') if name in installed), None)
    missing = ([] if pretendard else ['Pretendard']) + ([] if 'D2Coding' in installed else ['D2Coding'])
    if missing:
        raise RuntimeError('먼저 글꼴을 설치하세요: ' + ', '.join(missing) +
                           ' · 개인 글꼴로 설치한 후 다시 적용하세요.')
    return pretendard


def plan():
    pretendard = required_fonts()
    result = []
    def key(file, group, name, desired):
        item = dict(kind='key', file=file, group=group, key=name)
        item.update(old=read(item), installed=desired)
        result.append(item)
    for group, name in [('General', name) for name in
                        ('font', 'menuFont', 'toolBarFont', 'smallestReadableFont', 'fixed')] + [('WM', 'activeFont')]:
        old = read_key(CONFIG / 'kdeglobals', group, name)
        key('kdeglobals', group, name, font('D2Coding' if name == 'fixed' else pretendard,
                                           old, 8 if name == 'smallestReadableFont' else 10))
    profile = dict(kind='profile')
    if read(profile) is not None:
        raise RuntimeError('GF63-D2Coding.profile이 이미 있습니다. 기존 프로필을 보존하기 위해 중단했습니다.')
    parent = read_key(CONFIG / 'konsolerc', 'Desktop Entry', 'DefaultProfile')
    if parent == PROFILE_NAME:
        raise RuntimeError('Konsole 기본 프로필 참조가 올바르지 않습니다.')
    # Inherit the user's shell, colors and other settings without editing their profile.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / PROFILE_NAME
        write_key(path, 'General', 'Name', 'GF63 D2Coding')
        if parent:
            write_key(path, 'General', 'Parent', parent)
        write_key(path, 'Appearance', 'Font', font('D2Coding', size=11))
        profile.update(old=None, installed=path.read_text())
    result.append(profile)
    key('konsolerc', 'Desktop Entry', 'DefaultProfile', PROFILE_NAME)
    return result


def restore_items(state):
    for item in reversed(state):
        if read(item) == item['installed']:
            write(item, item['old'])


def configure(restore=False):
    gnome = environment() == 'gnome'
    backup = GNOME_BACKUP if gnome else BACKUP
    if restore:
        if gnome:
            disable_startup()
        if backup.exists():
            restore_items(json.loads(backup.read_text()))
            backup.unlink()
        return '글꼴 설정을 복원했습니다. 변경된 사용자 설정은 유지합니다. 앱을 재시작하거나 다시 로그인하세요.'
    if environment() not in ('kde', 'gnome'):
        raise RuntimeError('KDE Plasma 또는 GNOME 세션에서 적용하세요.')
    if backup.exists():
        return status()  # Repeated apply must not overwrite subsequent customization.
    state = gnome_plan() if gnome else plan()
    configure_mac.save(state, backup)
    try:
        for item in state:
            write(item, item['installed'])
    except Exception as exc:
        try:
            restore_items(state)
            backup.unlink()
        except Exception as rollback:
            raise RuntimeError(f'{exc} · 복원 실패: {rollback} · 백업을 유지했습니다. 복원을 다시 실행하세요.') from exc
        raise
    return status() + ('\n앱을 재시작하거나 다시 로그인하세요.' if gnome else
                       '\n다시 로그인하고 모든 Konsole 창을 종료한 뒤 실행하세요.')


def status():
    gnome = environment() == 'gnome'
    backup = GNOME_BACKUP if gnome else BACKUP
    target = 'GNOME: Pretendard / 고정폭: D2Coding' if gnome else 'KDE: Pretendard / Konsole: D2Coding'
    if gnome:
        target += ' · 로그인 시 적용 ' + ('켜짐' if startup_enabled() else '꺼짐')
    if environment() not in ('kde', 'gnome'):
        return 'KDE Plasma 또는 GNOME에서 사용할 수 있습니다.'
    if not backup.exists():
        return '미적용 · ' + target
    state = json.loads(backup.read_text())
    count = sum(read(item) == item['installed'] for item in state)
    return f'글꼴 설정 {count}/{len(state)}개 일치 · ' + target


def startup_enabled():
    return AUTOSTART.is_file() and not AUTOSTART.is_symlink() and AUTOSTART.read_text() == AUTOSTART_TEXT


def disable_startup():
    if startup_enabled():
        AUTOSTART.unlink()
        return 'GNOME 로그인 시 글꼴 적용을 해제했습니다.'
    if AUTOSTART.exists():
        return '사용자가 변경한 자동 시작 파일은 유지했습니다.'
    return 'GNOME 로그인 시 글꼴 적용이 꺼져 있습니다.'


def apply():
    if environment() not in ('kde', 'gnome'):
        raise RuntimeError('KDE Plasma 또는 GNOME 세션에서 적용하세요.')
    import install_fonts
    message = install_fonts.install()
    return message + '\n' + configure()


def enable_startup():
    if environment() != 'gnome':
        raise RuntimeError('GNOME 세션에서 자동 시작을 설정하세요.')
    if AUTOSTART.is_symlink() or (AUTOSTART.exists() and not startup_enabled()):
        raise RuntimeError('사용자가 만든 자동 시작 파일을 유지합니다: ' + str(AUTOSTART))
    message = apply()
    AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=AUTOSTART.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(AUTOSTART_TEXT)
        os.replace(name, AUTOSTART)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return message + '\nGNOME 로그인 시 글꼴 설치·적용 확인을 켰습니다.'


def login():
    if environment() != 'gnome' or not startup_enabled():
        return 'GNOME 글꼴 자동 시작이 비활성 상태입니다.'
    return apply()


def dispatch(operation):
    operations = {'apply': apply, 'status': status, 'restore': lambda: configure(restore=True),
                  'enable-startup': enable_startup, 'disable-startup': disable_startup, 'login': login}
    if operation not in operations:
        raise ValueError('지원하지 않는 글꼴 동작입니다.')
    return operations[operation]()


def main():
    parser = argparse.ArgumentParser(description='KDE·GNOME Pretendard / 고정폭·Konsole D2Coding 글꼴 설정')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--restore', action='store_true')
    group.add_argument('--status', action='store_true')
    group.add_argument('--enable-startup', action='store_true')
    group.add_argument('--disable-startup', action='store_true')
    group.add_argument('--login', action='store_true')
    args = parser.parse_args()
    try:
        operation = next((key.replace('_', '-') for key, value in vars(args).items() if value), 'apply')
        print(dispatch(operation))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
