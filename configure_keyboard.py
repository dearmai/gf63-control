"""Per-user IBus Hangul / X11 Caps Lock setup with ownership-aware restore."""
import ast
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
BACKUP = CONFIG / 'gf63-control/keyboard-backup.json'
AUTOSTART = CONFIG / 'autostart/gf63-control-keyboard.desktop'
SCHEMA = 'org.freedesktop.ibus.engine.hangul'
DESKTOP = '''[Desktop Entry]
Type=Application
Name=GF63 Control Korean Keyboard
Comment=Use Caps Lock for Korean/English switching
Exec=/usr/bin/python3 /usr/share/gf63-control/configure_xfce.py --apply-keyboard
OnlyShowIn=XFCE;KDE;
Terminal=false
StartupNotify=false
'''
# Exact previous app output; do not accept arbitrary files with a matching name.
LEGACY_DESKTOP = DESKTOP.replace('OnlyShowIn=XFCE;KDE;', 'OnlyShowIn=XFCE;')
OWNED_DESKTOPS = (DESKTOP, LEGACY_DESKTOP)


def run(*args, input=None):
    return subprocess.run(args, input=input, text=True, capture_output=True,
                          check=True, timeout=10).stdout.strip()


def keymap():
    result = {}
    for line in run('xmodmap', '-pke').splitlines():
        match = re.fullmatch(r'keycode\s+(\d+)\s*=\s*(.*)', line)
        if match:
            result[match[1]] = match[2].split()
    return result


def lock_keys():
    for line in run('xmodmap', '-pm').splitlines():
        if re.match(r'^lock\s', line):
            return re.findall(r'(\S+)\s+\(0x[0-9a-f]+\)', line)
    raise RuntimeError('X11 Lock modifier를 읽을 수 없습니다.')


def save(state):
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def clear_caps_lock():
    x11 = ctypes.CDLL('libX11.so.6')
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XkbLockModifiers.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    x11.XkbLockModifiers.restype = ctypes.c_int
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError('X11 디스플레이에 연결할 수 없습니다.')
    try:
        if not x11.XkbLockModifiers(display, 0x100, 2, 0):
            raise RuntimeError('Caps Lock 대문자 고정을 해제하지 못했습니다.')
    finally:
        x11.XCloseDisplay(display)


def apply_mapping(state, restore=False):
    current = keymap().get(state['code'])
    # Leave a mapping changed by the user after setup alone.
    if current not in (state['old_map'], state['installed_map']):
        print('사용자가 변경한 Caps Lock 키 설정을 유지합니다.')
        return
    locks = lock_keys()
    expected = state['installed_locks'] if restore else state['old_locks']
    target = state['old_locks'] if restore else state['installed_locks']
    symbols = state['old_map'] if restore else state['installed_map']
    if restore and current != state['installed_map']:
        return
    commands = []
    # Only restore the modifier when its value is still ours.
    if locks == expected or locks == target:
        commands.append('clear Lock')
        if target:
            commands.append('add Lock = ' + ' '.join(target))
    commands.insert(0, 'keycode ' + state['code'] + ' = ' + ' '.join(symbols))
    if not restore and locks == state['old_locks'] and 'Caps_Lock' in locks:
        clear_caps_lock()
    run('xmodmap', '-', input='\n'.join(commands) + '\n')
    if keymap().get(state['code']) != symbols:
        raise RuntimeError('Caps Lock 키 설정을 적용하지 못했습니다.')


def configure(restore=False, login=False):
    state = json.loads(BACKUP.read_text()) if BACKUP.exists() else None
    if restore:
        if state is None:
            return
        apply_mapping(state, restore=True)
        if run('gsettings', 'get', SCHEMA, 'switch-keys') == state['installed_switch']:
            run('gsettings', 'set', SCHEMA, 'switch-keys', state['old_switch'])
        if AUTOSTART.exists() and AUTOSTART.read_text() in OWNED_DESKTOPS:
            if state['old_autostart'] is None:
                AUTOSTART.unlink()
            else:
                AUTOSTART.write_text(state['old_autostart'])
        BACKUP.unlink()
        return
    if login:
        if state is not None:
            apply_mapping(state)
        return
    current_autostart = AUTOSTART.read_text() if AUTOSTART.exists() else None
    if (state is not None and current_autostart is not None
            and current_autostart not in (*OWNED_DESKTOPS, state['old_autostart'])):
        raise RuntimeError('기존 자동 시작 파일과 충돌합니다: ' + str(AUTOSTART))
    old_switch = run('gsettings', 'get', SCHEMA, 'switch-keys')
    if state is None:
        maps = keymap()
        codes = [code for code, symbols in maps.items() if 'Caps_Lock' in symbols]
        if len(codes) != 1:
            raise RuntimeError('Caps Lock 키를 하나로 식별할 수 없습니다. 기존 키 재매핑을 확인하세요.')
        code = codes[0]
        locks = lock_keys()
        switches = ast.literal_eval(old_switch).split(',')
        if 'Hangul' not in switches:
            switches.append('Hangul')
        state = dict(code=code, old_map=maps[code],
                     installed_map=['Hangul', 'NoSymbol', 'Hangul'],
                     old_locks=locks, installed_locks=[key for key in locks if key != 'Caps_Lock'],
                     old_switch=old_switch, installed_switch=repr(','.join(filter(None, switches))),
                     old_autostart=AUTOSTART.read_text() if AUTOSTART.exists() else None)
        save(state)  # Persist originals before any desktop mutation.
    if old_switch in (state['old_switch'], state['installed_switch']):
        run('gsettings', 'set', SCHEMA, 'switch-keys', state['installed_switch'])
    apply_mapping(state)
    AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    if not AUTOSTART.exists() or AUTOSTART.read_text() in (state['old_autostart'], *OWNED_DESKTOPS):
        AUTOSTART.write_text(DESKTOP)
    else:
        raise RuntimeError('기존 자동 시작 파일과 충돌합니다: ' + str(AUTOSTART))
    print('한/영 및 Caps Lock 한영 전환 설정 완료 (IBus 한글 입력기).')


def status():
    """Read actual mapping and persistence for the control panel."""
    if not BACKUP.exists():
        return '미설정 · 한/영 + Caps Lock 적용 버튼으로 설정하세요.'
    state = json.loads(BACKUP.read_text())
    switches = ast.literal_eval(run('gsettings', 'get', SCHEMA, 'switch-keys')).split(',')
    active = (keymap().get(state['code']) == state['installed_map']
              and lock_keys() == state['installed_locks'] and 'Hangul' in switches)
    persistent = AUTOSTART.exists() and AUTOSTART.read_text() == DESKTOP
    if not active:
        return '설정 확인 필요 · 현재 키 매핑 또는 입력기 설정이 변경되었습니다.'
    if not persistent:
        return '한/영 + Caps Lock 적용됨 · 로그인 자동 적용 설정을 확인하세요.'
    return '한/영 + Caps Lock 적용됨 · 로그인 시 자동 적용'
