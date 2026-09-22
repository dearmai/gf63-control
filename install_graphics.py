"""Read-only NVIDIA driver diagnosis; installation runs in the user's terminal.

The GUI stays unprivileged. This module never elevates and never calls the root
helper: package installation needs apt, which runs arbitrary maintainer scripts,
so it is handed to a terminal where the user authenticates with sudo themselves.
"""
import re
import shutil
import subprocess
from pathlib import Path

# Only the distribution's own driver packages, never an arbitrary command.
PACKAGE = re.compile(r'nvidia-driver-[0-9]{2,4}(-open|-server|-server-open)?\Z')
VENDOR = '[10de:'
# "-e" takes the remaining arguments on every terminal listed here.
TERMINALS = (('gnome-terminal', ('--',)), ('xfce4-terminal', ('-x',)),
             ('konsole', ('-e',)), ('mate-terminal', ('-x',)), ('tilix', ('-e',)),
             ('x-terminal-emulator', ('-e',)))
PRIME_MODES = ('on-demand', 'nvidia', 'intel')


def run(*args, timeout=30):
    """Return stdout, or None when the tool is missing or fails."""
    if not shutil.which(args[0]):
        return None
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def apt_based():
    return bool(shutil.which('apt-get') and shutil.which('dpkg'))


def card():
    """The discrete NVIDIA display device and the kernel driver bound to it."""
    output = run('lspci', '-nnk')
    if output is None:
        return None
    found = current = None
    for line in output.splitlines():
        if not line[:1].isspace():
            display = re.search(r'(VGA compatible controller|3D controller) \[\d+\]', line)
            current = {'name': line, 'driver': None} if display and VENDOR in line else None
            found = found or current
        elif current is not None:
            match = re.search(r'Kernel driver in use:\s*(\S+)', line)
            if match:
                current['driver'] = match[1]
    return found


def model(found):
    match = re.search(r'\[((?:GeForce|NVIDIA|Quadro|RTX)[^\]]*)\]', found['name'])
    return match[1] if match else 'NVIDIA GPU'


def secure_boot():
    """True, False, or None when the state cannot be read."""
    output = run('mokutil', '--sb-state')
    if output is None:
        return None
    text = output.lower()
    if 'disabled' in text:
        return False
    return True if 'enabled' in text else None


def kernel_headers():
    release = run('uname', '-r')
    if release is None:
        return None
    return Path('/lib/modules', release.strip(), 'build').exists()


def recommended():
    """The package ubuntu-drivers marks as recommended for this machine."""
    output = run('ubuntu-drivers', 'devices', timeout=60)
    if output is None:
        return None
    for line in output.splitlines():
        if 'recommended' not in line:
            continue
        match = re.search(r'driver\s*:\s*(\S+)', line)
        if match and PACKAGE.fullmatch(match[1]):
            return match[1]
    return None


def installed():
    """Installed nvidia-driver metapackage and its version, if any."""
    output = run('dpkg-query', '-W', '-f', '${Package} ${Version} ${Status}\n', 'nvidia-driver-*')
    for line in (output or '').splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1] == 'installed' and PACKAGE.fullmatch(parts[0]):
            return parts[0], parts[1]
    return None


def prime_mode():
    output = run('prime-select', 'query')
    mode = (output or '').strip()
    return mode if mode in PRIME_MODES else None


def driver_version():
    """Version reported by the running module, not by the package database."""
    output = run('nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader')
    version = (output or '').strip().splitlines()
    return version[0].strip() if version else None


def commands(package=None, mode='on-demand'):
    package = package or recommended()
    if package is None:
        raise RuntimeError('설치할 드라이버 패키지를 확인하지 못했습니다. '
                           'ubuntu-drivers devices 결과를 확인하세요.')
    if not PACKAGE.fullmatch(package):
        raise ValueError('허용하지 않는 드라이버 패키지 이름입니다: ' + package)
    if mode not in PRIME_MODES:
        raise ValueError('PRIME 모드는 ' + ', '.join(PRIME_MODES) + '만 지원합니다.')
    return ['sudo apt update', 'sudo apt install ' + package,
            'sudo prime-select ' + mode, 'sudo reboot']


def script(package=None, mode='on-demand'):
    update, install, prime, _ = commands(package, mode)
    return ('\n'.join([
        "echo 'GF63 Control · NVIDIA 그래픽 드라이버 설치'",
        "echo '관리자 암호를 입력하세요. 설치 내용을 확인한 뒤 진행 여부를 선택할 수 있습니다.'",
        'echo',
        update + ' || exit 1',
        install + ' || exit 1',
        # prime-select only exists once nvidia-prime is installed.
        'command -v prime-select >/dev/null && ' + prime,
        'echo',
        "echo '설치가 끝났습니다. 재부팅한 뒤 제어판에서 상태 확인을 누르세요.'",
        "read -r -p '창을 닫으려면 Enter를 누르세요. ' _",
    ]) + '\n')


def terminal():
    for name, flags in TERMINALS:
        path = shutil.which(name)
        if path:
            return [path, *flags]
    return None


def unavailable(found=None):
    """Why this control cannot be offered here, or None when it can."""
    if not apt_based():
        return 'apt 계열 배포판 전용입니다. 이 시스템의 패키지 관리자에 맞는 방법으로 설치하세요.'
    if found is None and card() is None:
        return 'NVIDIA 그래픽 카드를 찾지 못했습니다.'
    return None


def status():
    found = card()
    reason = unavailable(found)
    if reason:
        return reason
    current = found['driver']
    active = bool(current and current.startswith('nvidia'))
    lines = ['그래픽 카드 · ' + model(found)]
    if active:
        version = driver_version()
        lines.append('현재 드라이버 · ' + current + (' ' + version if version else ''))
    else:
        lines.append('현재 드라이버 · ' + (current or '없음') + ' · NVIDIA 독점 드라이버 미사용')
    have = installed()
    if have:
        lines.append('설치된 패키지 · ' + have[0] + ' ' + have[1] +
                     ('' if active else ' · 재부팅이 필요합니다'))
    else:
        lines.append('권장 패키지 · ' + (recommended() or '확인 실패 · 인터넷과 저장소 설정을 확인하세요'))
    boot = secure_boot()
    lines.append('Secure Boot · ' + ('활성 · 설치 후 MOK 등록 화면에서 키를 등록해야 합니다' if boot
                                     else '비활성 · MOK 등록 불필요' if boot is False
                                     else '상태 확인 불가'))
    release = (run('uname', '-r') or '').strip()
    headers = kernel_headers()
    lines.append('커널 헤더 · ' + (release + ' 있음' if headers
                                 else release + ' 없음 · linux-headers 설치가 필요합니다'
                                 if headers is False else '확인 불가'))
    lines.append('PRIME 모드 · ' + (prime_mode() or '미설치'))
    return '\n'.join(lines)


def install(progress=None, package=None, mode='on-demand'):
    """Open a terminal running the install; the user authenticates there."""
    reason = unavailable()
    if reason:
        raise RuntimeError(reason)
    if kernel_headers() is False:
        raise RuntimeError('현재 커널의 헤더가 없어 드라이버를 빌드할 수 없습니다. '
                           'linux-headers 패키지를 먼저 설치하세요.')
    command = terminal()
    if command is None:
        raise RuntimeError('터미널 프로그램을 찾지 못했습니다. 명령 복사 후 직접 실행하세요.')
    text = script(package, mode)
    if progress:
        progress('터미널에서 설치를 진행하세요. 관리자 암호 입력이 필요합니다.')
    try:
        subprocess.Popen([*command, 'bash', '-c', text], stdin=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as exc:
        raise RuntimeError('터미널을 열지 못했습니다: ' + str(exc)) from exc
    return ('터미널에서 설치를 진행하세요.\n'
            '설치가 끝나면 재부팅한 뒤 상태 확인을 누르세요.')
