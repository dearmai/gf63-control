"""Fixed per-user KakaoTalk installation through Flatpak Wine; never root."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import urllib.parse
import urllib.request

import configure_keyboard as keyboard
import install_fonts

APP = 'org.winehq.Wine'
BRANCH = 'stable-25.08'
REF = APP + '/x86_64/' + BRANCH
URL = 'https://lk.kakaocdn.net/talkpc/talk/win32/x64/KakaoTalk_Setup.exe'
DATA = Path.home() / '.var/app' / APP / 'data'
PREFIX = DATA / 'kakaotalk'
EXE = PREFIX / 'drive_c/Program Files/Kakao/KakaoTalk/KakaoTalk.exe'
APPLICATIONS = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'applications'
LAUNCHER = APPLICATIONS / 'gf63-kakaotalk-wine.desktop'
ICON = APPLICATIONS.parent / 'icons/hicolor/256x256/apps/gf63-kakaotalk.png'
LOG = DATA / 'kakaotalk-install/install.log'
DESKTOP = """[Desktop Entry]
Type=Application
Name=카카오톡 (Wine)
Comment=Wine으로 실행하는 Windows 카카오톡
Exec=/usr/bin/flatpak run --branch=stable-25.08 --env=WINEPREFIX=/var/data/kakaotalk --env=WINEDLLOVERRIDES=winemenubuilder.exe=d --env=WINEDEBUG=-all --env=XMODIFIERS=@im={module} --command=wine org.winehq.Wine "/var/data/kakaotalk/drive_c/Program Files/Kakao/KakaoTalk/KakaoTalk.exe"
Icon=gf63-kakaotalk
Terminal=false
Categories=Network;InstantMessaging;
StartupWMClass=kakaotalk.exe
"""


def im_module():
    """Wine reaches the Hangul input method over XIM, so name the running one."""
    # The keyboard backup describes settings we own, not the current session.
    # In particular, old backups default to IBus even after switching to nimf.
    modifiers = os.environ.get('XMODIFIERS', '')
    for name in keyboard.LABELS:
        if modifiers == '@im=' + name:
            return name
    try:
        return keyboard.detect_method()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return keyboard.IBUS


def desktop_file():
    return DESKTOP.format(module=im_module())


def owned_launchers():
    # A launcher this app wrote for either input method is ours to rewrite.
    current = [DESKTOP.format(module=name) for name in keyboard.LABELS]
    return current + [entry.replace('Icon=gf63-kakaotalk\n', 'Icon=gf63-control\n')
                      for entry in current]


def executable_icon(data):
    """Extract the first PE icon group; no Windows code is executed.

    Bounds checks apply to both file offsets and resource-directory offsets.
    Only the fixed type -> name -> language resource hierarchy is followed.
    """
    def read(offset, size):
        if offset < 0 or size < 0 or offset + size > len(data):
            raise ValueError('잘못된 실행 파일 리소스 범위')
        return data[offset:offset + size]

    def unpack(fmt, offset):
        return struct.unpack(fmt, read(offset, struct.calcsize(fmt)))

    if read(0, 2) != b'MZ':
        raise ValueError('Windows 실행 파일이 아닙니다.')
    pe, = unpack('<I', 0x3c)
    if read(pe, 4) != b'PE\0\0':
        raise ValueError('PE 헤더가 없습니다.')
    section_count, = unpack('<H', pe + 6)
    optional_size, = unpack('<H', pe + 20)
    optional = pe + 24
    magic, = unpack('<H', optional)
    if magic not in (0x10b, 0x20b):
        raise ValueError('지원하지 않는 PE 형식입니다.')
    directories = 112 if magic == 0x20b else 96
    if optional_size < directories + 24 or not 1 <= section_count <= 96:
        raise ValueError('잘못된 PE 헤더 크기')
    directory_count, = unpack('<I', optional + directories - 4)
    if directory_count < 3:
        raise ValueError('아이콘 리소스가 없습니다.')
    sections = optional + optional_size

    def file_offset(rva, size):
        for i in range(section_count):
            _, address, raw_size, raw = unpack('<IIII', sections + 40 * i + 8)
            delta = rva - address
            if 0 <= delta and delta + size <= raw_size:
                read(raw + delta, size)
                return raw + delta
        raise ValueError('실행 파일 리소스 주소를 찾지 못했습니다.')

    resource_rva, resource_size = unpack('<II', optional + directories + 16)
    base = file_offset(resource_rva, resource_size)

    def resource(offset, size):
        if offset < 0 or offset + size > resource_size:
            raise ValueError('잘못된 리소스 디렉터리 범위')
        return read(base + offset, size)

    def entries(relative):
        header = resource(relative, 16)
        named, numbered = struct.unpack_from('<HH', header, 12)
        table = resource(relative + 16, 8 * (named + numbered))
        return dict(struct.iter_unpack('<II', table))

    def directory(entry):
        if not entry & 0x80000000:
            raise ValueError('리소스 디렉터리가 아닙니다.')
        return entries(entry & 0x7fffffff)

    def payload(entry):
        languages = directory(entry)
        leaf = next(iter(languages.values()))
        if leaf & 0x80000000:
            raise ValueError('잘못된 리소스 계층')
        rva, size, _, _ = struct.unpack('<IIII', resource(leaf, 16))
        if size > 16 * 1024 * 1024:
            raise ValueError('아이콘 리소스가 허용 크기를 초과했습니다.')
        return read(file_offset(rva, size), size)

    try:
        types = entries(0)
        icons = directory(types[3])  # RT_ICON
        groups = directory(types[14])  # RT_GROUP_ICON
        group = payload(next(iter(groups.values())))
        reserved, kind, count = struct.unpack_from('<HHH', group)
        if reserved or kind != 1 or not 1 <= count <= 256 or len(group) != 6 + count * 14:
            raise ValueError('잘못된 아이콘 그룹')
        header, body = bytearray(group[:6]), bytearray()
        for i in range(count):
            item = group[6 + 14 * i:20 + 14 * i]
            size, identifier = struct.unpack_from('<IH', item, 8)
            bitmap = payload(icons[identifier])
            if size != len(bitmap) or not size:
                raise ValueError('아이콘 크기가 일치하지 않습니다.')
            if len(body) + size > 16 * 1024 * 1024:
                raise ValueError('아이콘 그룹이 허용 크기를 초과했습니다.')
            header += item[:8] + struct.pack('<II', size, 6 + 16 * count + len(body))
            body += bitmap
        return bytes(header + body)
    except (KeyError, StopIteration, struct.error) as exc:
        raise ValueError('실행 파일의 아이콘을 찾지 못했습니다.') from exc


def install_icon():
    """Use the installed application's own icon, without shipping its artwork."""
    temporary = ICON.with_suffix('.tmp')
    try:
        import gi
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import GdkPixbuf

        with EXE.open('rb') as source:
            data = source.read(256 * 1024 * 1024 + 1)
        if len(data) > 256 * 1024 * 1024:
            raise ValueError('실행 파일이 허용 크기를 초과했습니다.')
        loader = GdkPixbuf.PixbufLoader.new_with_type('ico')
        loader.set_size(256, 256)
        loader.write(executable_icon(data))
        loader.close()
        pixbuf = loader.get_pixbuf()
        if pixbuf is None:
            raise ValueError('아이콘 이미지를 읽지 못했습니다.')
        ICON.parent.mkdir(parents=True, exist_ok=True)
        pixbuf.savev(str(temporary), 'png', [], [])
        temporary.chmod(0o644)
        temporary.replace(ICON)
    except Exception as exc:
        raise RuntimeError('카카오톡 아이콘 등록 실패: ' + str(exc)) from exc
    finally:
        temporary.unlink(missing_ok=True)
    if shutil.which('gtk-update-icon-cache'):
        run(['gtk-update-icon-cache', '-f', '-t', str(ICON.parents[2])])


def run(args, timeout=30):
    # Wine utilities can emit Windows code-page bytes alongside UTF-8 output.
    # Diagnostics must not abort an otherwise successful command; registry
    # readback below still validates the actual settings independently.
    result = subprocess.run(args, text=True, encoding='utf-8', errors='replace',
                            capture_output=True, timeout=timeout)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-1500:].strip()
                           or '명령 실행 실패: ' + args[0])
    return result.stdout.strip()


def wine(*args):
    return ['flatpak', 'run', '--branch=' + BRANCH, '--env=WINEPREFIX=/var/data/kakaotalk',
            '--env=WINEDLLOVERRIDES=winemenubuilder.exe=d', '--env=WINEDEBUG=-all',
            '--env=XMODIFIERS=@im=' + im_module(), '--command=wine', APP, *args]


def runtime_installed():
    if not shutil.which('flatpak'):
        return False
    result = subprocess.run(['flatpak', 'info', '--user', REF],
                            capture_output=True, timeout=10)
    return result.returncode == 0


def status():
    if not shutil.which('flatpak'):
        return 'Flatpak이 필요합니다. 배포판 패키지 관리자로 Flatpak을 설치해 주세요.'
    if not runtime_installed():
        return '미설치 · Wine 실행 환경과 카카오톡을 설치할 수 있습니다.'
    if not EXE.is_file():
        return 'Wine 준비됨 · 카카오톡 설치가 필요합니다.'
    if not LAUNCHER.is_file() or LAUNCHER.read_text() != desktop_file() or not ICON.is_file():
        return '카카오톡 설치됨 · 설치 / 설정 복구로 실행 메뉴를 등록하세요.'
    return '설치됨 · 앱 메뉴에서 ‘카카오톡 (Wine)’을 실행할 수 있습니다.'


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != 'https' or parsed.hostname != 'lk.kakaocdn.net':
            raise RuntimeError('공식 다운로드 서버 외부로의 이동을 중단했습니다.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(progress):
    target = DATA / 'kakaotalk-install/KakaoTalk_Setup.exe'
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.part')
    try:
        opener = urllib.request.build_opener(OfficialRedirect())
        start = time.monotonic()
        with opener.open(URL, timeout=30) as response, temporary.open('wb') as output:
            size = 0
            expected = int(response.headers.get('Content-Length', 0))
            while True:
                if time.monotonic() - start > 300:
                    raise RuntimeError('다운로드 제한 시간을 초과했습니다. 다시 시도해 주세요.')
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 256 * 1024 * 1024:
                    raise RuntimeError('설치 파일이 허용 크기를 초과했습니다.')
                output.write(chunk)
                progress('공식 설치 파일 다운로드 중… {} MB'.format(size // (1024 * 1024)))
        with temporary.open('rb') as downloaded:
            if downloaded.read(2) != b'MZ' or (expected and expected != size):
                raise RuntimeError('설치 파일 다운로드가 올바르게 완료되지 않았습니다.')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


TEXT_FONTS = (
    'Arial', 'Arial Unicode MS', 'Tahoma', 'Verdana', 'Calibri',
    'Segoe UI', 'Segoe UI Variable', 'Microsoft Sans Serif', 'MS Sans Serif',
    'MS Shell Dlg', 'MS Shell Dlg 2', 'Helv', 'Helvetica',
    'Malgun Gothic', '맑은 고딕', 'Gulim', '굴림', 'Dotum', '돋움',
)


def configure_text_fonts():
    """Unify text faces, including existing bitmap UI fonts, in this prefix."""
    contents = install_fonts.contents()  # Verify before touching installed fonts.
    fonts = PREFIX / 'drive_c/windows/Fonts'
    fonts.mkdir(parents=True, exist_ok=True)
    for name, data in contents.items():
        if name.startswith('pretendard/'):
            (fonts / Path(name).name).write_bytes(data)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    key = r'HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes'
    backup = LOG.parent / 'font-substitutes-before.reg'
    if not backup.exists():
        run(wine('reg', 'export', key, '/var/data/kakaotalk-install/font-substitutes-before.reg', '/y'))
    # Import Unicode directly, independent of the host's console code page.
    registry = ('Windows Registry Editor Version 5.00\n\n[HKEY_LOCAL_MACHINE'
                r'\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes' + ']\n')
    registry += ''.join('"' + name + '"="Pretendard"\n' for name in TEXT_FONTS)
    (LOG.parent / 'text-fonts.reg').write_text(registry, encoding='utf-16')
    run(wine('reg', 'import', '/var/data/kakaotalk-install/text-fonts.reg'))
    actual = LOG.parent / 'text-fonts-readback.reg'
    actual.unlink(missing_ok=True)
    run(wine('reg', 'export', key, '/var/data/kakaotalk-install/text-fonts-readback.reg', '/y'))
    verified = actual.read_text(encoding='utf-16')
    if any('"' + name + '"="Pretendard"' not in verified for name in TEXT_FONTS):
        raise RuntimeError('영문·한글 Pretendard 대체 글꼴 확인 실패')


def configure_rendering():
    """Use Winetricks' RGB ClearType values in this app's prefix only."""
    key = r'HKCU\Control Panel\Desktop'
    LOG.parent.mkdir(parents=True, exist_ok=True)
    backup = LOG.parent / 'font-rendering-before.reg'
    if not backup.exists():
        run(wine('reg', 'export', key, '/var/data/kakaotalk-install/font-rendering-before.reg', '/y'))
    settings = [('FontSmoothing', 'REG_SZ', '2'),
                ('FontSmoothingType', 'REG_DWORD', '2'),
                ('FontSmoothingOrientation', 'REG_DWORD', '1'),
                ('FontSmoothingGamma', 'REG_DWORD', '1400')]
    for name, kind, value in settings:
        run(wine('reg', 'add', key, '/v', name, '/t', kind, '/d', value, '/f'))
        actual = run(wine('reg', 'query', key, '/v', name))
        match = re.search(r'^\s*' + name + r'\s+' + kind + r'\s+(\S+)\s*$', actual, re.MULTILINE)
        try:
            valid = match and int(match[1], 0 if kind == 'REG_DWORD' else 10) == int(value)
        except ValueError:
            valid = False
        if not valid:
            raise RuntimeError('글꼴 다듬기 설정 확인 실패: ' + name)


def install(progress=lambda message: None):
    if os.geteuid() == 0:
        raise RuntimeError('데스크톱 사용자 계정에서 설치하세요.')
    if not shutil.which('flatpak'):
        raise RuntimeError('Flatpak을 먼저 설치해 주세요. 관리자 설치를 자동 실행하지 않습니다.')
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with (LOG.parent / 'install.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('다른 카카오톡 설치가 진행 중입니다.')
        # Do not overwrite a launcher that somebody customized.
        if LAUNCHER.exists() and LAUNCHER.read_text() not in owned_launchers():
            raise RuntimeError('기존 Wine 바로가기가 변경되어 있습니다: ' + str(LAUNCHER))
        if not runtime_installed():
            progress('Wine 실행 환경 설치 중… 처음 설치할 때는 수 분 걸릴 수 있습니다.')
            remotes = run(['flatpak', 'remotes', '--user', '--columns=name'])
            if 'flathub' not in remotes.splitlines():
                run(['flatpak', 'remote-add', '--user', '--if-not-exists', 'flathub',
                     'https://flathub.org/repo/flathub.flatpakrepo'], timeout=120)
            run(['flatpak', 'install', '--user', '-y', '--noninteractive', 'flathub', REF], timeout=1200)
            if not runtime_installed():
                raise RuntimeError('Wine 실행 환경 설치를 확인하지 못했습니다.')
        if not EXE.is_file():
            download(progress)
            progress('카카오톡 설치 중…')
            run(wine('/var/data/kakaotalk-install/KakaoTalk_Setup.exe', '/S'), timeout=300)
            if not EXE.is_file():
                raise RuntimeError('설치 후 카카오톡 실행 파일을 찾지 못했습니다.')
        progress('한글 글꼴과 실행 메뉴 설정 중…')
        configure_text_fonts()
        progress('글꼴 안티앨리어싱 설정 중…')
        configure_rendering()
        progress('카카오톡 아이콘 등록 중…')
        install_icon()
        APPLICATIONS.mkdir(parents=True, exist_ok=True)
        temporary = LAUNCHER.with_suffix('.tmp')
        temporary.write_text(desktop_file())
        temporary.replace(LAUNCHER)
        if shutil.which('update-desktop-database'):
            run(['update-desktop-database', str(APPLICATIONS)])
        return status() + '\n글꼴 다듬기 적용됨 · 이미 실행 중이면 카카오톡을 완전히 종료한 뒤 다시 실행하세요.'


def launch():
    if not EXE.is_file() or not runtime_installed():
        raise RuntimeError('카카오톡을 먼저 설치해 주세요.')
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with (LOG.parent / 'launch.log').open('a') as log:
        process = subprocess.Popen(wine(r'C:\Program Files\Kakao\KakaoTalk\KakaoTalk.exe'),
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   start_new_session=True)
    try:
        code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        return '카카오톡 실행을 요청했습니다. 카카오 계정 로그인은 직접 진행해 주세요.'
    if code:
        raise RuntimeError('카카오톡 실행 실패. 로그: ' + str(LOG.parent / 'launch.log'))
    return '실행 요청을 전달했습니다. 카카오톡 창을 확인해 주세요.'


def repair_fonts():
    if not EXE.is_file() or not runtime_installed():
        raise RuntimeError('카카오톡을 먼저 설치해 주세요.')
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with (LOG.parent / 'install.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('다른 설치·글꼴 설정 작업이 진행 중입니다.')
        configure_text_fonts()
        configure_rendering()
    return ('영문·한글 Pretendard와 ClearType RGB 적용을 확인했습니다.\n'
            '카카오톡을 트레이에서도 완전히 종료한 뒤 다시 실행하세요.')


def open_wine_settings():
    if not runtime_installed() or not PREFIX.is_dir():
        raise RuntimeError('카카오톡용 Wine 환경을 먼저 설치해 주세요.')
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with (LOG.parent / 'wine-settings.log').open('a') as log:
        process = subprocess.Popen(wine('winecfg.exe'), stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True)
    try:
        code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        return '카카오톡용 Wine 설정창 열기를 요청했습니다.'
    if code:
        raise RuntimeError('Wine 설정창 실행 실패. 로그: ' + str(LOG.parent / 'wine-settings.log'))
    return 'Wine 설정창 실행 요청을 전달했습니다.'
