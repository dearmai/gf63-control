#!/usr/bin/python3 -I
"""Restricted hardware writer. Installed root-owned and invoked by polkit."""
import sys
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

EC = Path('/sys/devices/platform/msi-ec')
PRESETS = {
    'quiet': {'epp': 'power', 'max': 60, 'turbo': False, 'fan': 'silent', 'boost': False},
    'balanced': {'epp': 'balance_performance', 'max': 100, 'turbo': True, 'fan': 'auto', 'boost': False},
    'performance': {'epp': 'performance', 'max': 100, 'turbo': True, 'fan': 'auto', 'boost': False},
}


def power_config(raw):
    data = dict(PRESETS[raw], mode=raw) if raw in PRESETS else json.loads(raw)
    if not isinstance(data, dict) or set(data) != {'epp', 'max', 'turbo', 'fan', 'boost', 'mode'}:
        raise ValueError('전원 설정 항목이 올바르지 않습니다.')
    if data['mode'] not in ('quiet', 'balanced', 'performance', 'custom'):
        raise ValueError('알 수 없는 전원 모드입니다.')
    if data['epp'] not in ('power', 'balance_power', 'balance_performance', 'performance'):
        raise ValueError('지원하지 않는 CPU 정책입니다.')
    if type(data['max']) is not int or not 20 <= data['max'] <= 100:
        raise ValueError('CPU 성능 상한은 20~100%입니다.')
    if type(data['turbo']) is not bool or type(data['boost']) is not bool:
        raise ValueError('터보와 팬 부스트는 켜기/끄기 값이어야 합니다.')
    if data['fan'] not in ('auto', 'silent'):
        raise ValueError('팬 모드는 자동 또는 저소음만 지원합니다.')
    return data


def profile_text(data):
    return ('[main]\nsummary=GF63 power controls\n\n'
            '[cpu]\ngovernor=powersave\nenergy_performance_preference=' + data['epp'] +
            '\nmin_perf_pct=10\nmax_perf_pct=' + str(data['max']) +
            '\nno_turbo=' + ('0' if data['turbo'] else '1') +
            '\n\n[sysfs]\n/sys/devices/platform/msi-ec/fan_mode=' + data['fan'] +
            '\n/sys/devices/platform/msi-ec/cooler_boost=' + ('on' if data['boost'] else 'off') + '\n')


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(content)
            os.fchmod(output.fileno(), 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def set_power(raw):
    data = power_config(raw)
    if not Path('/sys/devices/system/cpu/intel_pstate/max_perf_pct').exists():
        raise ValueError('이 전원 설정은 Intel P-State CPU에서 지원됩니다.')
    for path in (EC / 'fan_mode', EC / 'cooler_boost'):
        path.read_text()
    subprocess.run(['/usr/bin/systemctl', 'enable', '--now', 'tuned.service'], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    profile = Path('/etc/tuned/gf63-custom/tuned.conf')
    previous = profile.read_text() if profile.exists() else None
    active_path = Path('/etc/tuned/active_profile')
    previous_active = active_path.read_text().strip() if active_path.exists() else ''
    atomic_write(profile, profile_text(data))
    try:
        subprocess.run(['/usr/sbin/tuned-adm', 'profile', 'gf63-custom'], check=True, timeout=50,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Ensure the selected profile really is active before recording the preference.
        if Path('/etc/tuned/active_profile').read_text().strip() != 'gf63-custom':
            raise ValueError('전원 프로필 활성화를 확인하지 못했습니다.')
        expected = {
            Path('/sys/devices/system/cpu/intel_pstate/max_perf_pct'): str(data['max']),
            Path('/sys/devices/system/cpu/intel_pstate/no_turbo'): '0' if data['turbo'] else '1',
            EC / 'fan_mode': data['fan'], EC / 'cooler_boost': 'on' if data['boost'] else 'off',
        }
        for path in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/energy_performance_preference'):
            expected[path] = data['epp']
        for attempt in range(20):
            mismatches = [str(path) for path, value in expected.items() if path.read_text().strip() != value]
            if not mismatches:
                break
            time.sleep(.25)
        else:
            raise ValueError('전원 설정 검증 실패: ' + ', '.join(mismatches))
    except Exception:
        if previous is not None:
            atomic_write(profile, previous)
        elif profile.exists():
            profile.unlink()
        if previous_active:
            subprocess.run(['/usr/sbin/tuned-adm', 'profile', *previous_active.split()], timeout=50,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raise
    atomic_write(Path('/etc/gf63-control/power.json'), json.dumps(data))
    print(json.dumps(data))


def resolve(action, raw):
    if action == 'battery':
        value = int(raw)
        if not 10 <= value <= 100:
            raise ValueError('충전 상한은 10~100%입니다.')
        paths = list(Path('/sys/class/power_supply').glob('BAT*/charge_control_end_threshold'))
        if len(paths) != 1:
            raise ValueError('충전 제한 배터리를 하나로 식별할 수 없습니다.')
        return paths[0], str(value)
    if action == 'brightness':
        value = int(raw)
        if not 5 <= value <= 100:
            raise ValueError('화면 밝기는 5~100%입니다.')
        base = Path('/sys/class/backlight/intel_backlight')
        maximum = int((base / 'max_brightness').read_text())
        return base / 'brightness', str(max(1, round(maximum * value / 100)))
    if action == 'keyboard':
        value = int(raw)
        if value not in range(4):
            raise ValueError('키보드 조명은 0~3단계입니다.')
        return Path('/sys/class/leds/msiacpi::kbd_backlight/brightness'), str(value)
    if action in ('webcam', 'cooler_boost') and raw in ('on', 'off'):
        return EC / action, raw
    raise ValueError('지원하지 않는 제어 또는 값입니다.')


def main():
    try:
        if len(sys.argv) != 3:
            raise ValueError('제어 이름과 값이 필요합니다.')
        if sys.argv[1] == 'power':
            set_power(sys.argv[2])
            return 0
        target, value = resolve(*sys.argv[1:])
        # No arbitrary path, firmware override, shell command or raw EC access.
        before = target.read_text().strip()
        if before != value:
            target.write_text(value + '\n')
        actual = target.read_text().strip()
        if actual != value:
            raise ValueError(f'적용 확인 실패: 요청 {value}, 실제 {actual}')
        print(actual)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
