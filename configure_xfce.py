#!/usr/bin/python3
"""Install nonconflicting bindings and keep the original values for rollback."""
import json
from pathlib import Path
import subprocess
import sys
import re

import desktop_env
import configure_mac
import configure_lid
import configure_keyboard

BACKUP = Path.home() / '.config/gf63-control/xfce-backup.json'
CHANNEL = 'xfce4-keyboard-shortcuts'
BINDINGS = {
    'XF86AudioRaiseVolume': 'volume-up', 'XF86AudioLowerVolume': 'volume-down',
    'XF86AudioMute': 'mute', 'XF86AudioMicMute': 'mic-mute',
    '<Super>F5': 'webcam', '<Super>F6': 'touchpad', '<Super>F8': 'cooler_boost',
    '<Super>F9': 'mic-mute', '<Super>F10': None,
}


def query(channel, prop, *args):
    return subprocess.run(['xfconf-query', '-c', channel, '-p', prop, *args],
                          text=True, capture_output=True, check=False, timeout=10)


def main():
    if sys.argv[1:] in (['--mac-shortcuts'], ['--restore-mac-shortcuts']):
        print(configure_mac.configure(restore=sys.argv[1] == '--restore-mac-shortcuts'))
        return
    if desktop_env.kind() == 'kde' and sys.argv[1:] != ['--apply-keyboard']:
        import configure_kde
        restore = sys.argv[1:] == ['--restore']
        if restore:
            configure_lid.configure(restore=True)
            configure_kde.configure(restore=True)
        print(configure_kde.configure(restore=restore, profile='hardware'))
        return
    if sys.argv[1:] == ['--apply-keyboard']:
        configure_keyboard.configure(login=True)
        return
    backup = json.loads(BACKUP.read_text()) if BACKUP.exists() else {}
    if sys.argv[1:] == ['--restore']:
        configure_mac.configure(restore=True)
        configure_lid.configure(restore=True)
        configure_keyboard.configure(restore=True)
        for item in backup.values():
            channel, prop, kind, old, installed = item
            current = query(channel, prop)
            if current.returncode == 0 and current.stdout.strip() == installed:
                result = query(channel, prop, '-r') if old is None else query(channel, prop, '-s', old)
                if result.returncode:
                    raise RuntimeError(result.stderr)
        print('이 프로그램이 변경한 XFCE 설정을 복원했습니다.')
        return
    updates = [(CHANNEL, '/commands/custom/' + key, 'string',
                '/usr/bin/gf63-control' + (' --action ' + action if action else ''))
               for key, action in BINDINGS.items()]
    # XFCE power manager grabs brightness keys even when handling is disabled.
    # Let it handle them and observe actual hardware state for our OSD.
    for key in ('XF86MonBrightnessUp', 'XF86MonBrightnessDown', 'XF86KbdBrightnessUp',
                'XF86KbdBrightnessDown', 'XF86KbdLightOnOff'):
        prop = '/commands/custom/' + key
        current = query(CHANNEL, prop)
        if current.stdout.startswith('/usr/bin/gf63-control --action '):
            query(CHANNEL, prop, '-r')
    updates += [('xfce4-power-manager', '/xfce4-power-manager/handle-brightness-keys', 'bool', 'true'),
                ('xfce4-power-manager', '/xfce4-power-manager/show-brightness-popup', 'bool', 'false')]
    panel = subprocess.run(['xfconf-query', '-c', 'xfce4-panel', '-lv'],
                           text=True, capture_output=True, check=True, timeout=10).stdout
    for plugin in re.findall(r'^(/plugins/plugin-\d+)\s+pulseaudio\s*$', panel, re.M):
        updates.append(('xfce4-panel', plugin + '/enable-keyboard-shortcuts', 'bool', 'false'))
        current = query('xfce4-panel', plugin + '/show-notifications').stdout.strip()
        kind, value = ('uint', '0') if current.isdigit() else ('bool', 'false')
        updates.append(('xfce4-panel', plugin + '/show-notifications', kind, value))
    for channel, prop, kind, value in updates:
        original = query(channel, prop)
        old = original.stdout.strip() if original.returncode == 0 else None
        if channel == CHANNEL and old and old != value and old.replace('/usr/local/bin/gf63-control', '/usr/bin/gf63-control') != value:
            print('기존 단축키 유지:', prop, old)
            continue
        key = channel + ':' + prop
        if key not in backup:
            backup[key] = [channel, prop, kind, old, value]
        else:
            backup[key][2] = kind
            backup[key][4] = value
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_text(json.dumps(backup, ensure_ascii=False, indent=2))
        result = query(channel, prop, '-s', value) if old is not None else query(channel, prop, '-n', '-t', kind, '-s', value)
        if result.returncode:
            raise RuntimeError(result.stderr)
    configure_keyboard.configure()
    print('기능키와 대체 단축키 등록 완료. 백업:', BACKUP)


if __name__ == '__main__':
    main()
