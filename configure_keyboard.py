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
# Remote X11 clients may send Caps_Lock on a new keycode after the original
# Caps Lock keycode is remapped. Nimf can accept that keysym directly as well.
TOGGLE_KEYS = {IBUS: ('Hangul',), NIMF: ('Hangul', 'Caps_Lock')}
FUNCTION_KEYS = tuple('F' + str(number) for number in range(1, 21))
# nimf's key table stops at F12; IBus accepts every X11 function keysym.
METHOD_FUNCTION_KEYS = {IBUS: FUNCTION_KEYS, NIMF: FUNCTION_KEYS[:12]}
DESKTOP = '''[Desktop Entry]
Type=Application
Name=GF63 Control Korean Keyboard
Comment=Use Caps Lock for Korean/English switching
Exec=/usr/bin/python3 /usr/share/gf63-control/configure_xfce.py --watch-keyboard
OnlyShowIn=XFCE;KDE;GNOME;X-Cinnamon;
Terminal=false
StartupNotify=false
'''
# Exact previous app output; do not accept arbitrary files with a matching name.
PRE_CINNAMON_DESKTOP = DESKTOP.replace('GNOME;X-Cinnamon;', 'GNOME;')
ONESHOT_DESKTOP = PRE_CINNAMON_DESKTOP.replace('--watch-keyboard', '--apply-keyboard')
PRE_GNOME_DESKTOP = ONESHOT_DESKTOP.replace('OnlyShowIn=XFCE;KDE;GNOME;', 'OnlyShowIn=XFCE;KDE;')
LEGACY_DESKTOP = ONESHOT_DESKTOP.replace('OnlyShowIn=XFCE;KDE;GNOME;', 'OnlyShowIn=XFCE;')
OWNED_DESKTOPS = (DESKTOP, PRE_CINNAMON_DESKTOP, ONESHOT_DESKTOP, PRE_GNOME_DESKTOP, LEGACY_DESKTOP)


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


class _XkbState(ctypes.Structure):
    _fields_ = [('group', ctypes.c_ubyte), ('locked_group', ctypes.c_ubyte),
                ('base_group', ctypes.c_ushort), ('latched_group', ctypes.c_ushort),
                ('mods', ctypes.c_ubyte), ('base_mods', ctypes.c_ubyte),
                ('latched_mods', ctypes.c_ubyte), ('locked_mods', ctypes.c_ubyte),
                ('compat_state', ctypes.c_ubyte), ('grab_mods', ctypes.c_ubyte),
                ('compat_grab_mods', ctypes.c_ubyte), ('lookup_mods', ctypes.c_ubyte),
                ('compat_lookup_mods', ctypes.c_ubyte), ('ptr_buttons', ctypes.c_ushort)]


def caps_lock_state(clear=False):
    x11 = ctypes.CDLL('libX11.so.6')
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XkbLockModifiers.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    x11.XkbLockModifiers.restype = ctypes.c_int
    x11.XkbGetState.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(_XkbState)]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError('X11 디스플레이에 연결할 수 없습니다.')
    try:
        state = _XkbState()
        if x11.XkbGetState(display, 0x100, ctypes.byref(state)):
            raise RuntimeError('Caps Lock 대문자 고정 상태를 읽을 수 없습니다.')
        if clear and state.locked_mods & 2:
            if not x11.XkbLockModifiers(display, 0x100, 2, 0):
                raise RuntimeError('Caps Lock 대문자 고정을 해제하지 못했습니다.')
            if x11.XkbGetState(display, 0x100, ctypes.byref(state)) or state.locked_mods & 2:
                raise RuntimeError('Caps Lock 대문자 고정 해제를 확인하지 못했습니다.')
        return bool(state.locked_mods & 2)
    finally:
        x11.XCloseDisplay(display)


def clear_caps_lock():
    caps_lock_state(clear=True)


class _XkbMods(ctypes.Structure):
    _fields_ = [('mask', ctypes.c_ubyte), ('real_mods', ctypes.c_ubyte),
                ('vmods', ctypes.c_ushort)]


class _XkbInterpret(ctypes.Structure):
    _fields_ = [('sym', ctypes.c_ulong), ('flags', ctypes.c_ubyte),
                ('match', ctypes.c_ubyte), ('mods', ctypes.c_ubyte),
                ('virtual_mod', ctypes.c_ubyte), ('action', ctypes.c_ubyte * 8)]


class _XkbCompat(ctypes.Structure):
    _fields_ = [('interprets', ctypes.POINTER(_XkbInterpret)), ('groups', _XkbMods * 4),
                ('count', ctypes.c_ushort), ('size', ctypes.c_ushort)]


class _XkbDesc(ctypes.Structure):
    _fields_ = [('display', ctypes.c_void_p), ('flags', ctypes.c_ushort),
                ('device', ctypes.c_ushort), ('min_code', ctypes.c_ubyte),
                ('max_code', ctypes.c_ubyte), ('controls', ctypes.c_void_p),
                ('server', ctypes.c_void_p), ('map', ctypes.c_void_p),
                ('indicators', ctypes.c_void_p), ('names', ctypes.c_void_p),
                ('compat', ctypes.POINTER(_XkbCompat)), ('geometry', ctypes.c_void_p)]


def caps_lock_actions(value=None):
    """Change only Caps_Lock interpretations through the supported XKB API.

    Keeping the keysym lets nimf receive remote Caps Lock keys. NoAction disables
    their LockMods action, including keys dynamically registered by an X11 client.
    All other symbol interpretations and modifier bindings remain intact.
    """
    x11 = ctypes.CDLL('libX11.so.6')
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XkbGetKeyboard.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
    x11.XkbGetKeyboard.restype = ctypes.POINTER(_XkbDesc)
    x11.XkbSetCompatMap.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                  ctypes.POINTER(_XkbDesc), ctypes.c_int]
    x11.XkbFreeKeyboard.argtypes = [ctypes.POINTER(_XkbDesc), ctypes.c_uint, ctypes.c_int]
    x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError('X11 디스플레이에 연결할 수 없습니다.')
    desc = None
    try:
        desc = x11.XkbGetKeyboard(display, 0x7f, 0x100)
        if not desc or not desc.contents.compat:
            raise RuntimeError('Caps Lock의 XKB 동작을 읽을 수 없습니다.')
        compat = desc.contents.compat.contents
        entries = [compat.interprets[i] for i in range(compat.count)
                   if compat.interprets[i].sym == 0xffe5]  # XK_Caps_Lock
        current = [[entry.flags, entry.match, entry.mods, entry.virtual_mod,
                    list(entry.action)] for entry in entries]
        if not current:
            raise RuntimeError('Caps Lock의 XKB 동작을 찾을 수 없습니다.')
        if value is None:
            return current
        if (not isinstance(value, list) or len(value) != len(current)
                or any(not isinstance(record, list) or len(record) != 5
                       or record[:4] != old[:4] or not isinstance(record[4], list)
                       or len(record[4]) != 8
                       or any(type(byte) is not int or not 0 <= byte <= 255 for byte in record[4])
                       for record, old in zip(value, current))):
            raise ValueError('Caps Lock의 XKB 동작 형식이 올바르지 않습니다.')
        for entry, record in zip(entries, value):
            entry.action[:] = record[4]
        if not x11.XkbSetCompatMap(display, 1, desc, True):  # XkbSymInterpMask
            raise RuntimeError('Caps Lock의 대문자 고정 동작을 변경하지 못했습니다.')
        x11.XSync(display, False)
    finally:
        if desc:
            x11.XkbFreeKeyboard(desc, 0x7f, True)
        x11.XCloseDisplay(display)
    if caps_lock_actions() != value:
        raise RuntimeError('Caps Lock의 대문자 고정 동작 변경을 확인하지 못했습니다.')


def apply_caps_actions(state, restore=False):
    if 'old_caps_actions' not in state:
        return False
    current = caps_lock_actions()
    expected = state['installed_caps_actions'] if restore else state['old_caps_actions']
    target = state['old_caps_actions'] if restore else state['installed_caps_actions']
    if current not in (expected, target):
        return False  # Preserve an interpretation the user changed after setup.
    if current != target:
        caps_lock_actions(target)
    if not restore:
        clear_caps_lock()
    return True


def apply_mapping(state, restore=False, quiet=False):
    current = keymap().get(state['code'])
    if restore:
        apply_caps_actions(state, restore=True)
    # Leave a mapping changed by the user after setup alone.
    if current not in (state['old_map'], state['installed_map']):
        if not quiet:
            print('사용자가 변경한 Caps Lock 키 설정을 유지합니다.')
        return
    native_caps = apply_caps_actions(state) if not restore else False
    locks = lock_keys()
    expected = state['installed_locks'] if restore else state['old_locks']
    target = state['old_locks'] if restore else state['installed_locks']
    symbols = state['old_map'] if restore else state['installed_map']
    if current == symbols and (set(locks) == set(target) or native_caps):
        return
    commands = []
    # Only restore the modifier when its value is still ours.
    change_locks = set(locks) in (set(expected), set(target))
    if change_locks:
        # Preserve unrelated bindings, including X11's unnameable BadKey entries.
        # remove resolves keysyms before remapping; add resolves them afterwards.
        removed = [key for key in locks if key not in target]
        added = [key for key in target if key not in locks]
        if removed:
            commands.append('remove Lock = ' + ' '.join(removed))
    commands.append('keycode ' + state['code'] + ' = ' + ' '.join(symbols))
    if change_locks and added:
        commands.append('add Lock = ' + ' '.join(added))
    if (not restore and 'old_caps_actions' not in state
            and set(locks) == set(state['old_locks']) and 'Caps_Lock' in locks):
        clear_caps_lock()
    run('xmodmap', '-', input='\n'.join(commands) + '\n')
    if keymap().get(state['code']) != symbols:
        raise RuntimeError('Caps Lock 키 설정을 적용하지 못했습니다.')
    if change_locks and set(lock_keys()) != set(target):
        raise RuntimeError('Caps Lock 대문자 고정 설정을 적용하지 못했습니다.')


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
                     installed_switch=extend_switch(method, old_switch, TOGGLE_KEYS[method]),
                     old_autostart=AUTOSTART.read_text() if AUTOSTART.exists() else None)
        save(state)  # Persist originals before any desktop mutation.
    switch_owned = old_switch in (state['old_switch'], state['installed_switch'])
    if function_keys is not None and not switch_owned:
        raise RuntimeError('입력기 전환 키가 외부에서 변경되었습니다. 원래 키 설정 복원 후 다시 적용하세요.')
    if method == NIMF and switch_owned and 'old_caps_actions' not in state:
        actions = caps_lock_actions()
        state['old_caps_actions'] = actions
        state['installed_caps_actions'] = [record[:4] + [[0] * 8] for record in actions]
        save(state)  # Save the original XKB action before disabling Caps Lock.
    if switch_owned:
        selected = state.get('function_keys', []) if function_keys is None else function_keys
        installed_switch = extend_switch(method, state['old_switch'],
                                         list(TOGGLE_KEYS[method]) + selected)
        if installed_switch != state['installed_switch'] or selected != state.get('function_keys', []):
            if function_keys is not None:
                state['function_keys'] = selected
            state['installed_switch'] = installed_switch
            save(state)
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
    locks_ok = (caps_lock_actions() == state['installed_caps_actions'] and not caps_lock_state()
                if 'old_caps_actions' in state else set(lock_keys()) == set(state['installed_locks']))
    active = (keymap().get(state['code']) == state['installed_map'] and locks_ok
              and all(key in switches for key in TOGGLE_KEYS[method])
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
