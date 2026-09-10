import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import configure_keyboard as keyboard


class KeyboardTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(keyboard.desktop_env, 'x11', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name, value in [('BACKUP', root / 'backup.json'), ('AUTOSTART', root / 'keyboard.desktop')]:
            patcher = patch.object(keyboard, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.maps = {'66': ['Caps_Lock', 'NoSymbol', 'Caps_Lock']}
        self.locks = ['Caps_Lock']
        self.switch = "'Shift+space'"
        self.commands = []
        patcher = patch.object(keyboard, 'clear_caps_lock')
        self.clear_caps = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(keyboard, 'run', side_effect=self.run_command)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_command(self, *args, input=None):
        self.commands.append((args, input))
        if args == ('xmodmap', '-pke'):
            return '\n'.join('keycode ' + code + ' = ' + ' '.join(keys) for code, keys in self.maps.items())
        if args == ('xmodmap', '-pm'):
            return 'lock      ' + ' '.join(key + ' (0x42)' for key in self.locks)
        if args == ('xmodmap', '-'):
            for line in input.splitlines():
                if line.startswith('keycode '):
                    lhs, rhs = line.split(' = ')
                    self.maps[lhs.split()[1]] = rhs.split()
                elif line == 'clear Lock':
                    self.locks = []
                elif line.startswith('add Lock = '):
                    self.locks = line.split(' = ')[1].split()
            return ''
        if args[:2] == ('gsettings', 'get'):
            return self.switch
        if args[:2] == ('gsettings', 'set'):
            self.switch = args[-1]
            return ''
        self.fail(str(args))

    def test_setup_repeat_login_restore(self):
        keyboard.configure()
        self.clear_caps.assert_called_once()
        original = keyboard.BACKUP.read_text()
        keyboard.configure()
        self.assertEqual(keyboard.BACKUP.read_text(), original)
        self.assertEqual(self.maps['66'], ['Hangul', 'NoSymbol', 'Hangul'])
        self.assertEqual(self.locks, [])
        self.assertEqual(self.switch, "'Shift+space,Hangul'")
        self.maps['66'] = ['Caps_Lock', 'NoSymbol', 'Caps_Lock']
        self.locks = ['Caps_Lock']
        keyboard.configure(login=True)
        self.assertEqual(self.locks, [])
        keyboard.configure(restore=True)
        self.assertEqual(self.maps['66'], ['Caps_Lock', 'NoSymbol', 'Caps_Lock'])
        self.assertEqual(self.locks, ['Caps_Lock'])
        self.assertEqual(self.switch, "'Shift+space'")
        self.assertFalse(keyboard.AUTOSTART.exists())

    def test_user_changes_survive_restore_and_login(self):
        keyboard.configure()
        self.maps['66'] = ['Escape']
        self.switch = "'F12'"
        keyboard.AUTOSTART.write_text('user change')
        keyboard.configure(login=True)
        keyboard.configure(restore=True)
        self.assertEqual(self.maps['66'], ['Escape'])
        self.assertEqual(self.switch, "'F12'")
        self.assertEqual(keyboard.AUTOSTART.read_text(), 'user change')

    def test_unrelated_lock_modifier_preserved(self):
        self.locks.append('Shift_Lock')
        keyboard.configure()
        self.assertEqual(self.locks, ['Shift_Lock'])
        keyboard.configure(restore=True)
        self.assertEqual(self.locks, ['Caps_Lock', 'Shift_Lock'])

    def test_missing_caps_does_not_mutate(self):
        self.maps = {}
        with self.assertRaises(RuntimeError):
            keyboard.configure()
        self.assertFalse(keyboard.BACKUP.exists())
        self.assertFalse(any(args[:2] == ('gsettings', 'set') for args, _ in self.commands))

    def test_failed_apply_keeps_backup_for_recovery(self):
        with patch.object(keyboard, 'apply_mapping', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                keyboard.configure()
        state = json.loads(keyboard.BACKUP.read_text())
        self.assertEqual(state['old_map'], ['Caps_Lock', 'NoSymbol', 'Caps_Lock'])
        keyboard.configure(restore=True)
        self.assertEqual(self.switch, "'Shift+space'")

    def test_status_reads_actual_mapping_and_autostart(self):
        self.assertIn('미설정', keyboard.status())
        keyboard.configure()
        self.assertIn('로그인 시 자동 적용', keyboard.status())
        keyboard.AUTOSTART.unlink()
        self.assertIn('자동 적용 설정을 확인', keyboard.status())
        self.maps['66'] = ['Escape']
        self.assertIn('설정 확인 필요', keyboard.status())

    def test_status_detects_missing_hangul_switch(self):
        keyboard.configure()
        self.switch = "'F12'"
        self.assertIn('설정 확인 필요', keyboard.status())

    def test_upgrade_legacy_autostart_preserves_original_backup(self):
        keyboard.configure()
        original = keyboard.BACKUP.read_text()
        keyboard.AUTOSTART.write_text(keyboard.LEGACY_DESKTOP)
        keyboard.configure()
        self.assertEqual(keyboard.AUTOSTART.read_text(), keyboard.DESKTOP)
        self.assertEqual(keyboard.BACKUP.read_text(), original)
        keyboard.configure(restore=True)
        self.assertFalse(keyboard.AUTOSTART.exists())

    def test_restore_removes_owned_legacy_autostart(self):
        keyboard.configure()
        keyboard.AUTOSTART.write_text(keyboard.LEGACY_DESKTOP)
        keyboard.configure(restore=True)
        self.assertFalse(keyboard.AUTOSTART.exists())

    def test_upgrade_pre_gnome_autostart_login_and_restore(self):
        keyboard.configure()
        original = keyboard.BACKUP.read_text()
        keyboard.AUTOSTART.write_text(keyboard.PRE_GNOME_DESKTOP)
        self.assertIn('자동 적용 설정을 확인', keyboard.status())
        keyboard.configure()
        self.assertIn('OnlyShowIn=XFCE;KDE;GNOME;', keyboard.AUTOSTART.read_text())
        self.assertEqual(keyboard.BACKUP.read_text(), original)
        self.maps['66'] = ['Caps_Lock', 'NoSymbol', 'Caps_Lock']
        self.locks = ['Caps_Lock']
        keyboard.configure(login=True)
        self.assertEqual(self.maps['66'], ['Hangul', 'NoSymbol', 'Hangul'])
        self.assertEqual(self.locks, [])
        keyboard.configure(restore=True)
        self.assertFalse(keyboard.AUTOSTART.exists())
        self.assertEqual(self.maps['66'], ['Caps_Lock', 'NoSymbol', 'Caps_Lock'])

    def test_wayland_login_skips_mapping_and_apply_reports_unsupported(self):
        keyboard.configure()
        original = keyboard.BACKUP.read_text()
        self.commands.clear()
        with patch.object(keyboard.desktop_env, 'x11', return_value=False):
            keyboard.configure(login=True)
            self.assertIn('Wayland', keyboard.status())
            with self.assertRaisesRegex(RuntimeError, 'X11'):
                keyboard.configure()
        self.assertEqual(self.commands, [])
        self.assertEqual(keyboard.BACKUP.read_text(), original)

    def test_autostart_conflict_does_not_mutate_keyboard(self):
        keyboard.configure()
        keyboard.AUTOSTART.write_text(keyboard.LEGACY_DESKTOP + '# user edit\n')
        original = keyboard.BACKUP.read_text()
        self.commands.clear()
        with self.assertRaisesRegex(RuntimeError, '충돌'):
            keyboard.configure()
        self.assertEqual(self.commands, [])
        self.assertEqual(keyboard.BACKUP.read_text(), original)
        self.assertTrue(keyboard.AUTOSTART.read_text().endswith('# user edit\n'))
