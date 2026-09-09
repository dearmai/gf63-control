"""Opt-in XFCE Command-style shortcuts with ownership-aware rollback."""
import desktop_env
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

BACKUP = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'gf63-control/mac-shortcuts.json'
OPTIONS = BACKUP.with_name('mac-shortcut-options.json')
TERMINAL_MODES = ('clipboard', 'disabled')
CHANNEL = 'xfce4-keyboard-shortcuts'
KEYS = dict(zip('cvxazsftw', ('copy', 'paste', 'cut', 'select-all', 'undo', 'save', 'find', 'new-tab', 'close-tab')))
BINDINGS = {'/commands/custom/<Super>' + key: '/usr/bin/gf63-mac-shortcut ' + action
            for key, action in KEYS.items()}
BINDINGS.update({
    '/commands/custom/<Shift><Super>z': '/usr/bin/gf63-mac-shortcut redo',
    '/commands/custom/<Super>space': 'xfce4-appfinder',
    '/xfwm4/custom/<Super>Tab': 'cycle_windows_key',
    '/xfwm4/custom/<Shift><Super>Tab': 'cycle_reverse_windows_key',
})


def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True, timeout=8).stdout.strip()


def properties():
    return dict(line.split(None, 1) for line in run('xfconf-query', '-c', CHANNEL, '-lv').splitlines()
                if len(line.split(None, 1)) == 2)


def canonical(prop):
    shortcut = prop.split('/', 3)[-1]
    modifiers = {value.lower().replace('primary', 'control') for value in re.findall(r'<([^>]+)>', shortcut)}
    return frozenset(modifiers), re.sub(r'<[^>]+>', '', shortcut).lower()


def write(prop, value):
    current = properties().get(prop)
    args = ['xfconf-query', '-c', CHANNEL, '-p', prop]
    if value is None:
        if current is not None:
            run(*args, '-r')
    else:
        run(*args, *([] if current is not None else ['-n', '-t', 'string']), '-s', value)
    if properties().get(prop) != value:
        raise RuntimeError('단축키 설정 확인 실패: ' + prop)


def save(state, path=None):
    path = path or BACKUP
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(state, output, ensure_ascii=False, indent=2)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)



def terminal_mode():
    mode = json.loads(OPTIONS.read_text()).get('terminal', 'clipboard') if OPTIONS.exists() else 'clipboard'
    if mode not in TERMINAL_MODES:
        raise ValueError('지원하지 않는 터미널 단축키 모드입니다.')
    return mode


def set_terminal_mode(mode):
    if mode not in TERMINAL_MODES:
        raise ValueError('지원하지 않는 터미널 단축키 모드입니다.')
    save({'terminal': mode}, OPTIONS)
    if terminal_mode() != mode:
        raise RuntimeError('터미널 단축키 설정 확인 실패')


def conflicts(prop, value, values, state):
    owned = state.get(prop)
    if owned and values.get(prop) != owned['installed']:
        return True
    for other, current in values.items():
        if '/custom/' not in other or canonical(other) != canonical(prop):
            continue
        if other == prop and (current == value or
                (prop == '/xfwm4/custom/<Super>Tab' and current == 'switch_window_key' and not owned)):
            continue
        return True
    return False


def configure(restore=False):
    if desktop_env.kind() == 'kde':
        import configure_kde
        return configure_kde.configure(restore=restore)
    if not restore:
        desktop_env.require_shortcuts()
    state = json.loads(BACKUP.read_text()) if BACKUP.exists() else {}
    if restore:
        for prop, item in list(state.items()):
            if properties().get(prop) == item['installed']:
                write(prop, item['old'])
            del state[prop]
            save(state)
        if BACKUP.exists():
            BACKUP.unlink()
        return status()
    # Refuse to edit inactive custom providers; don't replace unrelated defaults.
    values = properties()
    if any(values.get('/' + provider + '/custom/override') != 'true' for provider in ('commands', 'xfwm4')):
        raise RuntimeError('XFCE 사용자 단축키가 활성화되지 않았습니다. 키보드·창 관리자 설정을 확인하세요.')
    run('xdotool', 'version')
    previous = dict(state)
    changes = []
    try:
        for prop, value in BINDINGS.items():
            values = properties()
            if conflicts(prop, value, values, state):
                continue
            if prop not in state:
                state[prop] = {'old': values.get(prop), 'installed': value}
            save(state)  # Save originals before any mutation.
            changes.append((prop, values.get(prop), value))
            write(prop, value)
    except Exception as exc:
        try:
            for prop, old, installed in reversed(changes):
                if properties().get(prop) == installed:
                    write(prop, old)
            if previous:
                save(previous)
            elif BACKUP.exists():
                BACKUP.unlink()
        except Exception as rollback:
            raise RuntimeError(f'{exc}; 복원 실패: {rollback}. 원래 설정 복원을 실행하세요.') from exc
        raise
    return status()


def status():
    if desktop_env.kind() == 'kde':
        import configure_kde
        return configure_kde.status()
    if not desktop_env.x11():
        return 'Mac 단축키 변환은 X11 세션에서 지원합니다.'
    if not BACKUP.exists():
        return '꺼짐 · Mac 스타일 적용 버튼으로 켜세요.'
    state = json.loads(BACKUP.read_text())
    values = properties()
    active = [prop for prop, value in BINDINGS.items()
              if prop in state and values.get(prop) == value]
    missing = [prop.split('/', 3)[-1] for prop in BINDINGS if prop not in active]
    message = f'Mac 스타일 {len(active)}/{len(BINDINGS)}개 적용 · 다음 로그인에도 유지'
    if missing:
        message += '\n기존 설정 유지 / 미적용: ' + ', '.join(missing)
    return message
