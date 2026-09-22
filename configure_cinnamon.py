"""Opt-in Cinnamon screenshot shortcuts with ownership-aware rollback.

Cinnamon has no xfconf. Its keybindings live in GSettings, but applets and
desklets keep their own accelerators in JSON under ~/.config/cinnamon/spices,
and those grab the key first, so both are searched before writing. Accelerators
are compared by modifier set, since <Shift><Super>s and <Super><Shift>s are the
same combination. Only the screenshot media key is written, and only with a
value from a fixed list, so nothing typed elsewhere can reach gsettings.
"""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import desktop_env

BACKUP = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'gf63-control/cinnamon-shortcuts.json'
SCHEMA = 'org.cinnamon.desktop.keybindings.media-keys'
# Every schema whose id starts with this holds Cinnamon accelerators.
KEYBINDINGS = 'org.cinnamon.desktop.keybindings'
CUSTOM_LIST = (KEYBINDINGS, 'custom-list')
CUSTOM_PATH = 'org.cinnamon.desktop.keybindings.custom-keybinding:/org/cinnamon/desktop/keybindings/custom-keybindings/%s/'
# Applets and desklets keep their own accelerators in JSON, not in GSettings.
SPICES = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'cinnamon/spices'
ACTION = 'area-screenshot-clip'
LABEL = '영역 선택 후 클립보드로 복사'
# Fixed allowlist; never write an accelerator that came from user input.
CHOICES = (('<Super><Shift>s', 'Super + Shift + S · Windows 방식'),
           ('<Control><Shift>Print', 'Ctrl + Shift + PrtSc · Cinnamon 기본'),
           ('<Super>Print', 'Super + PrtSc'),
           ('<Super><Shift>4', 'Super + Shift + 4 · Mac 방식'))
BINDINGS = tuple(binding for binding, _ in CHOICES)
DEFAULT = BINDINGS[0]


def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True, timeout=8).stdout.strip()


def string_list(text):
    text = text.strip()
    if text.startswith('@as '):  # gsettings prints an empty array as "@as []".
        text = text[4:].strip()
    return [str(item) for item in ast.literal_eval(text)]


def variant(values):
    return '@as []' if not values else '[' + ', '.join(repr(value) for value in values) + ']'


def schemas():
    return set(run('gsettings', 'list-schemas').splitlines())


def unavailable():
    """Why this control cannot be offered here, or None when it can."""
    if desktop_env.kind() != 'cinnamon':
        return '화면 영역 캡처 단축키는 Cinnamon 세션에서 지원합니다.'
    if SCHEMA not in schemas():
        return 'Cinnamon 키보드 설정 스키마를 찾을 수 없습니다.'
    if ACTION not in run('gsettings', 'list-keys', SCHEMA).split():
        return '이 Cinnamon 버전에는 영역 캡처 단축키 항목이 없습니다.'
    return None


def canonical(accelerator):
    """Compare by modifier set and key, so <Shift><Super>s == <Super><Shift>s."""
    modifiers = {name.lower().replace('primary', 'control')
                 for name in re.findall(r'<([^>]+)>', accelerator)}
    return frozenset(modifiers), re.sub(r'<[^>]+>', '', accelerator).strip().lower()


def accelerators(schema, key):
    return string_list(run('gsettings', 'get', schema, key))


def gsettings_holders():
    """Every Cinnamon accelerator in GSettings, as (label, accelerator)."""
    installed = schemas()
    targets = [name for name in installed if name.startswith(KEYBINDINGS)]
    if CUSTOM_LIST[0] in installed:
        try:
            for entry in string_list(run('gsettings', 'get', *CUSTOM_LIST)):
                targets.append(CUSTOM_PATH % entry)
        except (ValueError, SyntaxError, subprocess.SubprocessError):
            pass
    for target in targets:
        try:
            lines = run('gsettings', 'list-recursively', target).splitlines()
        except subprocess.SubprocessError:
            continue
        for line in lines:
            parts = line.split(None, 2)
            if len(parts) != 3 or (parts[0], parts[1]) == (SCHEMA, ACTION):
                continue
            try:
                values = string_list(parts[2])
            except (ValueError, SyntaxError):
                continue
            for value in values:
                yield parts[1], value


def spice_holders():
    """Accelerators set on Cinnamon applets and desklets, from their JSON."""
    try:
        files = sorted(SPICES.glob('*/*.json'))
    except OSError:
        return
    for path in files:
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key, entry in data.items():
            value = entry.get('value') if isinstance(entry, dict) else None
            if not isinstance(value, str) or '<' not in value:
                continue
            for accelerator in value.split('::'):
                if accelerator:
                    yield '%s %s' % (path.parent.name, key), accelerator


def write(binding):
    run('gsettings', 'set', SCHEMA, ACTION, variant(binding))
    if accelerators(SCHEMA, ACTION) != binding:
        raise RuntimeError('단축키 설정 확인 실패: ' + ACTION)


def holder(binding):
    """The other Cinnamon action already bound to this accelerator, if any."""
    wanted = canonical(binding)
    for label, accelerator in list(gsettings_holders()) + list(spice_holders()):
        if canonical(accelerator) == wanted:
            return label
    return None


def save(state):
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=BACKUP.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(state, output, ensure_ascii=False, indent=2)
        os.replace(name, BACKUP)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def selected():
    """The binding this app last applied, for the UI to preselect."""
    if not BACKUP.exists():
        return None
    installed = json.loads(BACKUP.read_text()).get('installed', [])
    return installed[0] if installed else None


def configure(binding=None, restore=False):
    state = json.loads(BACKUP.read_text()) if BACKUP.exists() else None
    if restore:
        if state is None:
            return status()
        reason = unavailable()
        if reason:
            raise RuntimeError(reason)
        # Only give back what is still ours.
        if accelerators(SCHEMA, ACTION) == state['installed']:
            write(state['old'])
        BACKUP.unlink()
        return status()
    reason = unavailable()
    if reason:
        raise RuntimeError(reason)
    binding = binding or DEFAULT
    if binding not in BINDINGS:
        raise ValueError('지원하지 않는 단축키입니다: ' + str(binding))
    current = accelerators(SCHEMA, ACTION)
    if state is not None and current not in (state['old'], state['installed']):
        raise RuntimeError('영역 캡처 단축키가 외부에서 변경되었습니다. '
                           '원래 설정 복원 후 다시 적용하세요.')
    other = holder(binding)
    if other:
        raise RuntimeError('이미 다른 기능이 쓰는 단축키입니다: ' + other)
    old = state['old'] if state is not None else current
    save({'old': old, 'installed': [binding]})  # Persist the original first.
    write([binding])
    return status()


def status():
    reason = unavailable()
    if reason:
        return reason
    current = accelerators(SCHEMA, ACTION)
    pretty = dict(CHOICES)
    if not BACKUP.exists():
        if not current:
            return '미설정 · 영역 캡처 단축키가 비어 있습니다.'
        return '기본 설정 사용 중 · ' + pretty.get(current[0], current[0])
    state = json.loads(BACKUP.read_text())
    if current != state['installed']:
        return '설정 확인 필요 · 단축키가 외부에서 변경되었습니다: ' + (', '.join(current) or '없음')
    return pretty.get(current[0], current[0]) + ' 적용됨 · ' + LABEL
