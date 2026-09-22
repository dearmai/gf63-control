"""Per-user Hangul input method / X11 Caps Lock setup with ownership-aware restore.

Supports the two Korean input methods shipped by the targeted distributions:
IBus (Rocky 9) and nimf (HamoniKR and other Debian-family images).
"""
import ast
import ctypes
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time
import desktop_env

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
BACKUP = CONFIG / 'gf63-control/keyboard-backup.json'
AUTOSTART = CONFIG / 'autostart/gf63-control-keyboard.desktop'
IBUS = 'ibus'
NIMF = 'nimf'
SCHEMAS = {IBUS: 'org.freedesktop.ibus.engine.hangul',
           NIMF: 'org.nimf.engines.nimf-libhangul'}
LABELS = {IBUS: 'IBus', NIMF: 'nimf'}
# nimf switches to Korean and back through two separate shortcut lists.
NIMF_SHORTCUTS = ('shortcuts-to-lang', 'shortcuts-to-sys')
FUNCTION_KEYS = tuple('F' + str(number) for number in range(1, 21))
# nimf's key table stops at F12; IBus accepts every X11 function keysym.
METHOD_FUNCTION_KEYS = {IBUS: FUNCTION_KEYS, NIMF: FUNCTION_KEYS[:12]}
DESKTOP = '''[Desktop Entry]
Type=Application
Name=GF63 Control Korean Keyboard
Comment=Use Caps Lock for Korean/English switching
Exec=/usr/bin/python3 /usr/share/gf63-control/configure_xfce.py --watch-keyboard
OnlyShowIn=XFCE;KDE;GNOME;
Terminal=false
StartupNotify=false
'''
# Exact previous app output; do not accept arbitrary files with a matching name.
ONESHOT_DESKTOP = DESKTOP.replace('--watch-keyboard', '--apply-keyboard')
PRE_GNOME_DESKTOP = ONESHOT_DESKTOP.replace('OnlyShowIn=XFCE;KDE;GNOME;', 'OnlyShowIn=XFCE;KDE;')
LEGACY_DESKTOP = ONESHOT_DESKTOP.replace('OnlyShowIn=XFCE;KDE;GNOME;', 'OnlyShowIn=XFCE;')
OWNED_DESKTOPS = (DESKTOP, ONESHOT_DESKTOP, PRE_GNOME_DESKTOP, LEGACY_DESKTOP)


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


def apply_mapping(state, restore=False, quiet=False):
    current = keymap().get(state['code'])
    # Leave a mapping changed by the user after setup alone.
    if current not in (state['old_map'], state['installed_map']):
        if not quiet:
            print('사용자가 변경한 Caps Lock 키 설정을 유지합니다.')
        return
    locks = lock_keys()
    expected = state['installed_locks'] if restore else state['old_locks']
    target = state['old_locks'] if restore else state['installed_locks']
    symbols = state['old_map'] if restore else state['installed_map']
    if current == symbols and locks == target:
        return
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


def installed_schemas():
    return set(run('gsettings', 'list-schemas').splitlines())


def running_processes():
    """Read /proc directly; the watcher must not fork a tool for this."""
    names = set()
    try:
        entries = list(Path('/proc').iterdir())
    except OSError:
        return names
    for entry in entries:
        if entry.name.isdigit():
            try:
                names.add((entry / 'comm').read_text().strip())
            except OSError:
                continue
    return names


def detect_method():
    """Pick the Hangul input method actually in use, never both at once."""
    schemas = installed_schemas()
    available = [name for name in (NIMF, IBUS) if SCHEMAS[name] in schemas]
    if not available:
        raise RuntimeError('한글 입력기 설정을 찾을 수 없습니다. nimf 또는 IBus 한글 입력기를 설치하세요.')
    if len(available) == 1:
        return available[0]
    running = running_processes()
    modules = (os.environ.get('GTK_IM_MODULE', '') + ':' +
               os.environ.get('QT_IM_MODULE', '') + ':' +
               os.environ.get('XMODIFIERS', '')).lower()
    for name in available:
        # The daemons are named after the method: nimf, ibus-daemon, ibus-x11.
        if any(comm.split('-')[0] == name for comm in running):
            return name
    for name in available:
        if name in modules:
            return name
    raise RuntimeError('한글 입력기가 nimf와 IBus 중 무엇인지 확인할 수 없습니다. 사용할 입력기를 실행한 뒤 다시 시도하세요.')


def method_of(state):
    # Backups written before nimf support was added always described IBus.
    return state.get('input_method', IBUS) if state else detect_method()


def active_method():
    """Configured or detected method for the UI; None when unavailable."""
    try:
        return method_of(json.loads(BACKUP.read_text()) if BACKUP.exists() else None)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return None


def method_label():
    return LABELS.get(active_method(), '한글 입력기')


def supported_function_keys():
    return METHOD_FUNCTION_KEYS.get(active_method(), FUNCTION_KEYS)


def string_list(text):
    text = text.strip()
    if text.startswith('@as '):  # gsettings prints an empty array as "@as []".
        text = text[4:].strip()
    return [str(item) for item in ast.literal_eval(text)]


def variant(keys):
    return '@as []' if not keys else '[' + ', '.join(repr(key) for key in keys) + ']'


def read_switch(method):
    """Return the switch-key setting as one opaque, canonical string."""
    if method == NIMF:
        return json.dumps([string_list(run('gsettings', 'get', SCHEMAS[NIMF], key))
                           for key in NIMF_SHORTCUTS])
    return run('gsettings', 'get', SCHEMAS[IBUS], 'switch-keys')


def write_switch(method, value):
    if method == NIMF:
        for key, keys in zip(NIMF_SHORTCUTS, json.loads(value)):
            run('gsettings', 'set', SCHEMAS[NIMF], key, variant(keys))
        return
    run('gsettings', 'set', SCHEMAS[IBUS], 'switch-keys', value)


def switch_keys(method, value):
    """Keys that toggle Korean input, for status and ownership checks."""
    if method == NIMF:
        to_lang, to_sys = json.loads(value)
        return [key for key in to_lang if key in to_sys]
    return [key for key in ast.literal_eval(value).split(',') if key]


def extend_switch(method, value, keys):
    if method == NIMF:
        lists = [list(group) for group in json.loads(value)]
        for group in lists:
            group.extend(key for key in keys if key not in group)
        return json.dumps(lists)
    switches = switch_keys(IBUS, value)
    switches.extend(key for key in keys if key not in switches)
    return repr(','.join(switches))


def selected_function_keys():
    if not BACKUP.exists():
        return []
    return json.loads(BACKUP.read_text()).get('function_keys', [])


def configure(restore=False, login=False, function_keys=None):
    # Serialize the watcher with manual apply/restore. In particular, a watcher
    # must not reapply a stale backup while restore is removing that backup.
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    with (BACKUP.parent / 'keyboard-settings.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _configure(restore=restore, login=login, function_keys=function_keys)
    if not restore and not login:
        start_watcher()


def start_watcher():
    """Activate the installed login service immediately after manual setup."""
    with (BACKUP.parent / 'keyboard-login.log').open('a') as log:
        subprocess.Popen(['/usr/bin/python3', '/usr/share/gf63-control/configure_xfce.py',
                          '--watch-keyboard'], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)


def _configure(restore=False, login=False, function_keys=None):
    if function_keys is not None:
        if isinstance(function_keys, str) or any(key not in FUNCTION_KEYS for key in function_keys):
            raise ValueError('한영 전환 기능키는 F1~F20만 선택할 수 있습니다.')
        function_keys = [key for key in FUNCTION_KEYS if key in function_keys]
    if not desktop_env.x11():
        if login:
            return  # Do not change an Xwayland-only map in a Wayland session.
        raise RuntimeError('한/영 + Caps Lock 설정은 X11 전용입니다. GNOME on Xorg 세션에서 사용하세요.')
    state = json.loads(BACKUP.read_text()) if BACKUP.exists() else None
    if restore:
        if state is None:
            return
        method = method_of(state)
        apply_mapping(state, restore=True)
        if read_switch(method) == state['installed_switch']:
            write_switch(method, state['old_switch'])
        if AUTOSTART.exists() and AUTOSTART.read_text() in OWNED_DESKTOPS:
            if state['old_autostart'] is None:
                AUTOSTART.unlink()
            else:
                AUTOSTART.write_text(state['old_autostart'])
        BACKUP.unlink()
        return
    if login:
        if state is not None:
            method = method_of(state)
            current_switch = read_switch(method)
            if current_switch == state['old_switch'] and current_switch != state['installed_switch']:
                write_switch(method, state['installed_switch'])
            apply_mapping(state, quiet=True)
        return
    method = method_of(state)
    if function_keys and any(key not in METHOD_FUNCTION_KEYS[method] for key in function_keys):
        raise ValueError(LABELS[method] + ' 한글 입력기는 ' +
                         METHOD_FUNCTION_KEYS[method][-1] + '까지만 한영 전환 키로 등록할 수 있습니다.')
    current_autostart = AUTOSTART.read_text() if AUTOSTART.exists() else None
    if (state is not None and current_autostart is not None
            and current_autostart not in (*OWNED_DESKTOPS, state['old_autostart'])):
        raise RuntimeError('기존 자동 시작 파일과 충돌합니다: ' + str(AUTOSTART))
    old_switch = read_switch(method)
    if state is None:
        maps = keymap()
        codes = [code for code, symbols in maps.items() if 'Caps_Lock' in symbols]
        if len(codes) != 1:
            raise RuntimeError('Caps Lock 키를 하나로 식별할 수 없습니다. 기존 키 재매핑을 확인하세요.')
        code = codes[0]
        locks = lock_keys()
        state = dict(code=code, old_map=maps[code],
                     installed_map=['Hangul', 'NoSymbol', 'Hangul'],
                     old_locks=locks, installed_locks=[key for key in locks if key != 'Caps_Lock'],
                     input_method=method, old_switch=old_switch,
                     installed_switch=extend_switch(method, old_switch, ['Hangul']),
                     old_autostart=AUTOSTART.read_text() if AUTOSTART.exists() else None)
        save(state)  # Persist originals before any desktop mutation.
    if function_keys is not None and old_switch not in (state['old_switch'], state['installed_switch']):
        raise RuntimeError('입력기 전환 키가 외부에서 변경되었습니다. 원래 키 설정 복원 후 다시 적용하세요.')
    if function_keys is not None and function_keys != state.get('function_keys', []):
        state['function_keys'] = function_keys
        state['installed_switch'] = extend_switch(method, state['old_switch'],
                                                  ['Hangul'] + function_keys)
        save(state)
    if old_switch in (state['old_switch'], state['installed_switch']) or function_keys is not None:
        write_switch(method, state['installed_switch'])
    apply_mapping(state)
    AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    if not AUTOSTART.exists() or AUTOSTART.read_text() in (state['old_autostart'], *OWNED_DESKTOPS):
        AUTOSTART.write_text(DESKTOP)
    else:
        raise RuntimeError('기존 자동 시작 파일과 충돌합니다: ' + str(AUTOSTART))
    print('한/영 및 Caps Lock 한영 전환 설정 완료 (' + LABELS[method] + ' 한글 입력기).')


def watch_login():
    """Reconcile settings, never key events, across desktop/XKB resets.

    One process per configuration and X display. Stop after restore, autostart
    replacement, or repeated session failures. Every subprocess is time bounded.
    """
    if not desktop_env.x11() or not BACKUP.exists():
        return
    import hashlib
    display = hashlib.sha256(os.environ.get('DISPLAY', '').encode()).hexdigest()[:16]
    with (BACKUP.parent / ('keyboard-login-' + display + '.lock')).open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        failures = 0
        while BACKUP.exists() and AUTOSTART.exists() and AUTOSTART.read_text() == DESKTOP:
            try:
                configure(login=True)
                failures = 0
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                failures += 1
                if failures == 1:
                    print('한영 키 자동 적용 재시도: ' + str(exc), flush=True)
                if failures >= 30:
                    raise RuntimeError('한영 키 자동 적용 실패: 세션 연결을 확인하세요.') from exc
            time.sleep(2)


def status():
    """Read actual mapping and persistence for the control panel."""
    if not desktop_env.x11():
        return 'X11 전용 · Wayland에서는 한/영 + Caps Lock 자동 적용을 지원하지 않습니다.'
    if not BACKUP.exists():
        return '미설정 · 한/영 + Caps Lock 적용 버튼으로 설정하세요.'
    state = json.loads(BACKUP.read_text())
    method = method_of(state)
    switches = switch_keys(method, read_switch(method))
    active = (keymap().get(state['code']) == state['installed_map']
              and lock_keys() == state['installed_locks'] and 'Hangul' in switches
              and all(key in switches for key in state.get('function_keys', [])))
    persistent = AUTOSTART.exists() and AUTOSTART.read_text() == DESKTOP
    if not active:
        return '설정 확인 필요 · 현재 키 매핑 또는 입력기 설정이 변경되었습니다.'
    label = LABELS[method] + ' · 한/영 + Caps Lock'
    if state.get('function_keys'):
        label += ' + ' + ', '.join(state['function_keys'])
    if not persistent:
        return label + ' 적용됨 · 로그인 자동 적용 설정을 확인하세요.'
    return label + ' 적용됨 · 로그인 시 자동 적용'
