"""Install verified, bundled OFL fonts for the current user without networking."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

RESOURCES = Path(__file__).resolve().parent / 'vendor/fonts'
DESTINATION = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'fonts/gf63-control'


def contents():
    manifest = json.loads((RESOURCES / 'SHA256.json').read_text())
    result = {}
    for name, digest in manifest.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or relative.suffix not in ('.otf', '.ttf', '.txt'):
            raise ValueError('번들 글꼴 경로가 올바르지 않습니다.')
        data = (RESOURCES / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError('번들 글꼴 무결성 확인 실패: ' + name)
        result[name] = data
    if not any(name.endswith(('.otf', '.ttf')) for name in result):
        raise RuntimeError('번들에 글꼴이 없습니다.')
    return result


def install():
    files = contents()  # Validate the whole bundle before writing anything.
    if DESTINATION.is_symlink():
        raise RuntimeError('글꼴 설치 경로가 심볼릭 링크입니다.')
    if DESTINATION.exists():
        if any(not (DESTINATION / name).is_file() or (DESTINATION / name).read_bytes() != data
               for name, data in files.items()):
            raise RuntimeError('기존 GF63 글꼴 파일이 다릅니다. 사용자 파일을 유지했습니다: ' + str(DESTINATION))
        return '패키지 글꼴 설치 확인 완료'
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.gf63-fonts-', dir=DESTINATION.parent))
    created = False
    try:
        for name, data in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        os.rename(temporary, DESTINATION)
        created = True
        subprocess.run(['fc-cache', '-f', str(DESTINATION)], check=True,
                       text=True, capture_output=True, timeout=30)
    except Exception:
        if created:
            shutil.rmtree(DESTINATION)
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return '패키지 글꼴 설치 완료 (Pretendard · D2Coding)'
