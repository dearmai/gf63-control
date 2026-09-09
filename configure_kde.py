"""KDE KGlobalAccel desktop actions; fixed commands and reversible key assignments."""
import os
from pathlib import Path

import configure_mac as common
import desktop_env

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'gf63-control'
DATA = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'kglobalaccel'
META, SHIFT, TAB = 0x10000000, 0x02000000, 0x01000001


def modern_call(method, signature, values):
    # KF6 represents each QKeySequence as a struct containing an integer array.
    if method == 'shortcut':
        method = 'shortcutKeys'
    elif method == 'setShortcut':
        method, signature = 'setShortcutKeys', '(asa(ai)u)'
        values = (values[0], [([key] if isinstance(key, int) else key,) for key in values[1]], values[2])
    elif method == 'isGlobalShortcutAvailable':
        method, signature = 'globalShortcutAvailable', '((ai)s)'
        values = (([values[0]],), values[1])
    result = desktop_env.call('org.kde.kglobalaccel', '/kglobalaccel', 'org.kde.KGlobalAccel',
                              method, signature, values)
    if method in ('shortcutKeys', 'setShortcutKeys'):
        result = ([seq[0][0] if len(seq[0]) == 1 else list(seq[0]) for seq in result[0]],)
    return result


def call(method, signature, *values):
    if os.environ.get('KDE_SESSION_VERSION') == '6':
        return modern_call(method, signature, values)
    try:
        return desktop_env.call('org.kde.kglobalaccel', '/kglobalaccel', 'org.kde.KGlobalAccel',
                                method, signature, values)
    except Exception as exc:
        if 'UnknownMethod' not in str(exc):
            raise
        return modern_call(method, signature, values)


def specs(profile='mac'):
    result = {}
    commands = dict(common.KEYS, **{'Z': 'redo'}) if profile == 'mac' else {
        'F5': 'webcam', 'F6': 'touchpad', 'F8': 'cooler_boost', 'F9': 'mic-mute', 'F10': 'open'}
    for key, action in commands.items():
        component = f'gf63-{profile}-{action}.desktop'
        code = (0x01000030 + int(key[1:]) - 1) if key.startswith('F') else ord(key.upper())
        code |= META | (SHIFT if key == 'Z' else 0)
        command = ('/usr/bin/gf63-mac-shortcut ' + action) if profile == 'mac' else (
            '/usr/bin/gf63-control' + (' --action ' + action if action != 'open' else ''))
        result[action] = dict(identity=[component, '_launch', 'GF63 Control', action],
                              key=code, desktop=desktop_text(action, command))
    if profile == 'mac':
        result['launcher'] = dict(identity=['gf63-mac-launcher.desktop', '_launch', 'GF63 Control', '실행기'],
                                  key=META | 0x20, desktop=desktop_text('실행기', 'krunner'))
        for action, name, key in [('next-window', 'Walk Through Windows', META | TAB),
                                  ('previous-window', 'Walk Through Windows (Reverse)', META | SHIFT | TAB)]:
            result[action] = dict(identity=['kwin', name, 'KWin', name], key=key, desktop=None)
    return result


def desktop_text(name, command):
    return ('[Desktop Entry]\nType=Application\nName=GF63 ' + name + '\nExec=' + command +
            '\nNoDisplay=true\nStartupNotify=false\nTerminal=false\n')


def keys(identity):
    return list(call('shortcut', '(as)', identity)[0])


def set_keys(identity, values):
    call('doRegister', '(as)', identity)
    actual = list(call('setShortcut', '(asaiu)', identity, values, 6)[0])
    if actual != values or keys(identity) != values:
        raise RuntimeError('KDE 단축키 적용 확인 실패: ' + identity[3])


def backup(profile):
    return CONFIG / ('kde-' + profile + '-shortcuts.json')


def restore_item(item):
    identity = item['identity']
    if keys(identity) == item['installed_keys']:
        if item['old_keys']:
            set_keys(identity, item['old_keys'])
        elif item['desktop'] is not None:
            call('unregister', '(ss)', identity[0], identity[1])
        else:
            set_keys(identity, [])
    else:
        # A customized launcher must keep its desktop file to remain executable.
        return
    if item['desktop'] is not None:
        path = DATA / identity[0]
        if path.exists() and path.read_text() == item['desktop']:
            if item['old_file'] is None:
                path.unlink()
            else:
                path.write_text(item['old_file'])
    for other in item.get('displaced', []):
        if keys(other['identity']) == other['installed_keys']:
            set_keys(other['identity'], other['old_keys'])


# These stock Plasma 5 actions occupy the requested Mac chords. Only their
# exact stock single-key assignments may be displaced; custom bindings stay.
STOCK_CONFLICTS = {
    'paste': ('plasmashell', 'show-on-mouse-pos'),
    'save': ('plasmashell', 'stop current activity'),
    'new-tab': ('kwin', 'Edit Tiles'),
    'close-tab': ('kwin', 'Overview'),
    'next-window': ('plasmashell', 'next activity'),
    'previous-window': ('plasmashell', 'previous activity'),
}


def stock_conflicts(action, spec):
    if os.environ.get('KDE_SESSION_VERSION') == '6' or action not in STOCK_CONFLICTS:
        return None
    entries = call('getGlobalShortcutsByKey', '(i)', spec['key'])[0]
    if len(entries) != 1:
        return None
    name, friendly, component, component_friendly, context, _, current, defaults = entries[0]
    if (component, name) != STOCK_CONFLICTS[action] or context != 'default' or list(current) != [spec['key']]:
        return None
    if list(defaults) != [spec['key']] and not (action in ('next-window', 'previous-window') and not defaults):
        return None
    return [dict(identity=[component, name, component_friendly, friendly],
                 old_keys=list(current), installed_keys=[])]


def configure(restore=False, profile='mac'):
    import json
    path = backup(profile)
    state = json.loads(path.read_text()) if path.exists() else {}
    if restore:
        for action, item in list(state.items()):
            restore_item(item)
            del state[action]
            common.save(state, path)
        if path.exists(): path.unlink()
        return 'KDE 단축키를 복원했습니다.'
    desktop_env.require_shortcuts()
    definitions = specs(profile)
    added = []
    try:
        for action, spec in definitions.items():
            identity, key, content = spec['identity'], spec['key'], spec['desktop']
            old_keys = keys(identity)
            if action in state:
                continue  # Never overwrite a later KDE shortcut customization.
            displaced = []
            if not call('isGlobalShortcutAvailable', '(is)', key, identity[0])[0]:
                displaced = stock_conflicts(action, spec) if profile == 'mac' else None
                if displaced is None:
                    continue
            file = DATA / identity[0]
            old_file = file.read_text() if content is not None and file.exists() else None
            if old_file is not None and old_file != content:
                continue
            desired = old_keys + ([key] if key not in old_keys else [])
            item = dict(identity=identity, old_keys=old_keys, installed_keys=desired,
                        old_file=old_file, desktop=content, displaced=displaced)
            state[action] = item
            common.save(state, path)
            added.append(action)
            if content is not None:
                DATA.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            for other in displaced:
                set_keys(other['identity'], other['installed_keys'])
            set_keys(identity, desired)
    except Exception:
        # Failed registration can have no keys yet; include it in cleanup as well.
        for action in reversed(added):
            item = state[action]
            if keys(item['identity']) == item['old_keys']:
                item = dict(item, installed_keys=item['old_keys'])
            restore_item(item)
            del state[action]
            common.save(state, path)
        if not state and path.exists(): path.unlink()
        raise
    return status(profile)


def status(profile='mac'):
    import json
    if not desktop_env.x11():
        return 'Plasma Wayland · Mac 단축키 변환은 Plasma (X11)에서 지원합니다.'
    path = backup(profile)
    if not path.exists():
        return 'KDE 단축키 꺼짐 · 적용 버튼으로 켜세요.'
    state = json.loads(path.read_text())
    active = []
    for action, spec in specs(profile).items():
        if action in state and keys(spec['identity']) == state[action]['installed_keys']:
            file = DATA / spec['identity'][0]
            if spec['desktop'] is None or (file.exists() and file.read_text() == spec['desktop']):
                active.append(action)
    missing = [action for action in specs(profile) if action not in active]
    message = f'KDE 단축키 {len(active)}/{len(specs(profile))}개 적용 · 다음 로그인에도 유지'
    return message + ('\n기존 설정 유지 / 미적용: ' + ', '.join(missing) if missing else '')
