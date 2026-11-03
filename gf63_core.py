"""Read device state and dispatch a fixed set of desktop actions."""
import os
import configure_lid
import desktop_env
import json
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

EC = Path('/sys/devices/platform/msi-ec')
HELPER = '/usr/libexec/gf63-control-helper'
LABELS = {'brightness': '화면 밝기', 'keyboard': '키보드 조명',
          'volume': '스피커 음량', 'microphone': '마이크', 'touchpad': '터치패드',
          'webcam': '웹캠', 'cooler_boost': '팬 부스트', 'battery': '충전 상한', 'power': '전원 모드', 'lid': '덮개 닫고 사용'}


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60 if args[0] == 'pkexec' else 8,
                            env={**os.environ, 'LC_ALL': 'C'})
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or '명령 실행 실패')
    return result.stdout.strip()


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def number(path):
    try:
        return int(read(path))
    except (ValueError, TypeError):
        return None


def plank_processes(binary):
    """Find only this user's Plank instances on the current X11 display."""
    executable = Path(binary).resolve()
    display = os.environ.get('DISPLAY', '')
    bus = os.environ.get('DBUS_SESSION_BUS_ADDRESS', '')
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid() or (entry / 'exe').resolve() != executable:
                continue
            args = [os.fsdecode(value) for value in (entry / 'cmdline').read_bytes().split(b'\0') if value]
            env = dict(value.split(b'=', 1) for value in (entry / 'environ').read_bytes().split(b'\0') if b'=' in value)
            process_display = os.fsdecode(env.get(b'DISPLAY', b''))
            for index, arg in enumerate(args[1:], 1):
                if arg.startswith('--display='):
                    process_display = arg.split('=', 1)[1]
                elif arg == '--display' and index + 1 < len(args):
                    process_display = args[index + 1]
            if process_display != display or bus and os.fsdecode(env.get(b'DBUS_SESSION_BUS_ADDRESS', b'')) != bus:
                continue
            if args:
                found.append((int(entry.name), [binary] + args[1:]))
        except (OSError, ValueError):
            continue  # Processes may disappear while /proc is being read.
    return found


def plank_status():
    if not desktop_env.x11() or not os.environ.get('DISPLAY'):
        return 'Plank 재시작은 X11 데스크톱 세션에서 사용할 수 있습니다.', False
    binary = shutil.which('plank')
    if not binary:
        return 'Plank가 설치되어 있지 않습니다.', False
    running = plank_processes(binary)
    return ('Plank 실행 중 · 현재 화면의 도크를 재시작할 수 있습니다.' if running
            else 'Plank가 실행 중이 아닙니다. 버튼을 누르면 시작합니다.'), True


def restart_plank():
    message, available = plank_status()
    if not available:
        raise RuntimeError(message)
    binary = shutil.which('plank')
    previous = plank_processes(binary)
    for pid, _ in previous:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 5
    old_pids = {pid for pid, _ in previous}
    while old_pids.intersection(pid for pid, _ in plank_processes(binary)):
        if time.monotonic() >= deadline:
            raise RuntimeError('Plank가 종료되지 않아 재시작하지 못했습니다.')
        time.sleep(0.1)
    commands = [args for _, args in previous] or [[binary]]
    children = [subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                for args in commands]
    # A successful fork alone does not mean the dock started successfully.
    time.sleep(1)
    running = plank_processes(binary)
    if not running or any(child.poll() not in (None, 0) for child in children):
        raise RuntimeError('Plank 실행을 확인하지 못했습니다. 실행 환경과 도크 설정을 확인하세요.')
    return 'Plank를 다시 시작했습니다. 도크 위치를 확인하세요.', True


def parse_volume(text):
    match = re.fullmatch(r'Volume:\s+(\d+(?:\.\d+)?)(\s+\[MUTED\])?', text)
    if not match:
        raise ValueError('음량 응답을 읽을 수 없습니다.')
    return round(float(match[1]) * 100), bool(match[2])


def touchpads():
    if not desktop_env.x11():
        return []
    output = run('xinput', 'list', '--short')
    return re.findall(r'[^\n]*[Tt]ouchpad[^\n]*?id=(\d+)', output)


def touchpad_state():
    values = []
    for device in touchpads():
        match = re.search(r'Device Enabled \(\d+\):\s*(\d)', run('xinput', 'list-props', device))
        if match:
            values.append(match[1] == '1')
    return any(values) if values else None


def snapshot():
    data = {}
    try:
        lid = dict(line.split('=', 1) for line in run('systemctl', 'show', 'gf63-lid.service',
                   '--property=LoadState,ActiveState,UnitFileState').splitlines())
        data['lid'] = ('on' if configure_lid.current() == 'true' else 'conflict') if lid.get('ActiveState') == 'active' else (
            'off' if lid.get('ActiveState') == 'inactive' and lid.get('UnitFileState') == 'disabled' else 'failed')
        if lid.get('LoadState') != 'loaded':
            data['lid'] = None
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        data['lid'] = None
    base = Path('/sys/class/backlight/intel_backlight')
    current, maximum = number(base / 'brightness'), number(base / 'max_brightness')
    data['brightness'] = round(current * 100 / maximum) if current is not None and maximum else None
    data['keyboard'] = number('/sys/class/leds/msiacpi::kbd_backlight/brightness')
    for key in ('webcam', 'cooler_boost'):
        value = read(EC / key)
        data[key] = value == 'on' if value in ('on', 'off') else None
    batteries = list(Path('/sys/class/power_supply').glob('BAT*'))
    battery = batteries[0] if len(batteries) == 1 else Path('/nonexistent')
    data['battery'] = number(battery / 'charge_control_end_threshold')
    data['capacity'] = number(battery / 'capacity')
    data['charge_status'] = read(battery / 'status')
    data['cpu_temp'] = number(EC / 'cpu/realtime_temperature')
    data['cpu_max'] = number('/sys/devices/system/cpu/intel_pstate/max_perf_pct')
    data['no_turbo'] = number('/sys/devices/system/cpu/intel_pstate/no_turbo')
    data['epp'] = read('/sys/devices/system/cpu/cpufreq/policy0/energy_performance_preference')
    data['fan'] = read(EC / 'fan_mode')
    data['power'] = read('/etc/tuned/active_profile')
    if data['power'] == 'gf63-custom':
        try:
            data['power'] = json.loads(read('/etc/gf63-control/power.json') or '{}').get('mode', 'custom')
        except (ValueError, AttributeError):
            data['power'] = 'custom'
    for key, target in [('volume', '@DEFAULT_AUDIO_SINK@'), ('microphone', '@DEFAULT_AUDIO_SOURCE@')]:
        try:
            data[key] = parse_volume(run('wpctl', 'get-volume', target))
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
            data[key] = None
    try:
        data['touchpad'] = touchpad_state()
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        data['touchpad'] = None
    return data


def description(key, value):
    if value is None:
        return '사용할 수 없음'
    if key == 'lid':
        return {'on': '켜짐 · 화면만 끔', 'off': '꺼짐', 'conflict': '데스크톱 설정 확인 필요',
                'failed': '서비스 확인 필요'}.get(value, '확인 필요')
    if key == 'power':
        return {'quiet': '저소음', 'balanced': '일반', 'performance': '성능',
                'custom': '사용자 설정'}.get(value, '시스템: ' + str(value))
    if key in ('volume', 'microphone'):
        return '음소거' if value[1] else f'{value[0]}%'
    if key == 'keyboard':
        return '꺼짐' if value == 0 else f'{value} / 3단계'
    if isinstance(value, bool):
        return '켜짐' if value else '꺼짐'
    return f'{value}%'


def apply(action, value=None):
    if action == 'lid':
        if value not in ('on', 'off'):
            raise ValueError('덮개 설정은 on/off만 허용합니다.')
        if value == 'on':
            old = configure_lid.current()
            had_backup = configure_lid.backup_path().exists()
            try:
                configure_lid.configure()
                run('pkexec', HELPER, 'lid', value)
            except Exception:
                configure_lid.write(old)
                if not had_backup and configure_lid.backup_path().exists():
                    configure_lid.backup_path().unlink()
                raise
        else:
            run('pkexec', HELPER, 'lid', value)
            configure_lid.configure(restore=True)
    elif action == 'power':
        run('pkexec', HELPER, 'power', json.dumps(value) if isinstance(value, dict) else str(value))
    elif action in ('volume-up', 'volume-down'):
        run('wpctl', 'set-volume', '-l', '1.0', '@DEFAULT_AUDIO_SINK@',
            '5%+' if action.endswith('up') else '5%-')
    elif action in ('mute', 'mic-mute'):
        run('wpctl', 'set-mute', '@DEFAULT_AUDIO_SOURCE@' if action == 'mic-mute'
            else '@DEFAULT_AUDIO_SINK@', 'toggle')
    elif action in ('brightness-up', 'brightness-down', 'keyboard-up', 'keyboard-down', 'keyboard-toggle'):
        key = 'brightness' if action.startswith('brightness') else 'keyboard'
        state = snapshot()[key]
        if state is None:
            raise RuntimeError('밝기 제어 장치가 없습니다.')
        if key == 'keyboard':
            value = (state + 1) % 4 if action.endswith('toggle') else max(0, min(3, state + (1 if action.endswith('up') else -1)))
        else:
            value = max(5, min(100, state + (5 if action.endswith('up') else -5)))
        run('pkexec', HELPER, key, str(value))
    elif action in ('battery', 'brightness', 'keyboard'):
        run('pkexec', HELPER, action, str(int(value)))
    elif action in ('webcam', 'cooler_boost'):
        previous = read(EC / action)
        if previous not in ('on', 'off'):
            raise RuntimeError('장치 상태를 확인할 수 없습니다.')
        run('pkexec', HELPER, action, 'off' if previous == 'on' else 'on')
    elif action == 'touchpad':
        devices = touchpads()
        state = touchpad_state()
        if not devices or state is None:
            raise RuntimeError('터치패드를 찾을 수 없습니다.')
        for device in devices:
            run('xinput', 'set-prop', device, 'Device Enabled', '0' if state else '1')
    else:
        raise ValueError('알 수 없는 기능입니다.')
    return snapshot()
