import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import configure_keyboard as keyboard


class FakeSession:
    """X11 keymap and GSettings doubles shared by the per-input-method tests."""

    method = None

    def setUp(self):
        patcher = patch.object(keyboard.desktop_env, 'x11', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(keyboard, 'start_watcher')
        self.start_watcher = patcher.start()
        self.addCleanup(patcher.stop)
        root = Path(self.temp.name)
        for name, value in [('BACKUP', root / 'backup.json'), ('AUTOSTART', root / 'keyboard.desktop')]:
            patcher = patch.object(keyboard, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.maps = {'66': ['Caps_Lock', 'NoSymbol', 'Caps_Lock']}
        self.locks = ['Caps_Lock']
        self.switch = "'Shift+space'"
        self.nimf = {'shortcuts-to-lang': "['Hangul']", 'shortcuts-to-sys': "['Hangul']"}
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
        if args == ('gsettings', 'list-schemas'):
            return keyboard.SCHEMAS[self.method]
        if args[:2] == ('gsettings', 'get'):
            return self.nimf[args[3]] if args[2] == keyboard.SCHEMAS[keyboard.NIMF] else self.switch
        if args[:2] == ('gsettings', 'set'):
            if args[2] == keyboard.SCHEMAS[keyboard.NIMF]:
                self.nimf[args[3]] = args[-1]
            else:
                self.switch = args[-1]
            return ''
        self.fail(str(args))

class KeyboardTests(FakeSession, unittest.TestCase):
    method = keyboard.IBUS

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

    def test_all_function_keys_apply_update_restore(self):
        self.switch = "'Shift+space,F2'"
        keyboard.configure(function_keys=list(keyboard.FUNCTION_KEYS))
        self.assertEqual(keyboard.selected_function_keys(), list(keyboard.FUNCTION_KEYS))
        self.assertIn('F20', keyboard.status())
        self.assertEqual(self.maps['66'], ['Hangul', 'NoSymbol', 'Hangul'])
        keyboard.configure(function_keys=['F20'])
        self.assertEqual(self.switch, "'Shift+space,F2,Hangul,F20'")
        keyboard.configure(function_keys=[])
        self.assertEqual(self.switch, "'Shift+space,F2,Hangul'")
        keyboard.configure(restore=True)
        self.assertEqual(self.switch, "'Shift+space,F2'")

    def test_function_keys_upgrade_keeps_original_backup(self):
        keyboard.configure()
        keyboard.configure(function_keys=['F1', 'F20', 'F1'])
        keyboard.configure(login=True)
        keyboard.configure()
        self.assertEqual(self.switch, "'Shift+space,Hangul,F1,F20'")
        self.assertEqual(keyboard.selected_function_keys(), ['F1', 'F20'])
        self.switch = "'Shift+space,Hangul,F1'"
        self.assertIn('설정 확인 필요', keyboard.status())
        keyboard.configure(restore=True)
        self.assertEqual(self.switch, "'Shift+space,Hangul,F1'")

    def test_invalid_function_keys_do_not_mutate(self):
        for keys in [['F0'], ['F21'], ['F1,Escape'], 'F1']:
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                keyboard.configure(function_keys=keys)
        self.assertEqual(self.commands, [])
        self.assertFalse(keyboard.BACKUP.exists())

    def test_function_key_changes_preserve_external_switch_settings(self):
        keyboard.configure(function_keys=['F1'])
        original = keyboard.BACKUP.read_text()
        self.switch = "'F12'"
        for keys in [['F20'], ['F1']]:
            with self.assertRaisesRegex(RuntimeError, '외부'):
                keyboard.configure(function_keys=keys)
        self.assertEqual(self.switch, "'F12'")
        self.assertEqual(keyboard.BACKUP.read_text(), original)

    def test_oneshot_upgrade_keeps_backup_and_starts_watcher(self):
        keyboard.configure(function_keys=['F17'])
        original = keyboard.BACKUP.read_text()
        keyboard.AUTOSTART.write_text(keyboard.ONESHOT_DESKTOP)
        keyboard.configure()
        self.assertEqual(keyboard.BACKUP.read_text(), original)
        self.assertEqual(keyboard.AUTOSTART.read_text(), keyboard.DESKTOP)
        self.assertEqual(self.start_watcher.call_count, 2)
        keyboard.configure(restore=True)
        self.assertFalse(keyboard.AUTOSTART.exists())

    def test_login_reapplies_reset_switch_keys_without_overwriting_custom(self):
        keyboard.configure(function_keys=['F17'])
        self.switch = "'Shift+space'"
        keyboard.configure(login=True)
        self.assertEqual(self.switch, "'Shift+space,Hangul,F17'")
        self.switch = "'F12'"
        keyboard.configure(login=True)
        self.assertEqual(self.switch, "'F12'")

    def test_login_does_not_rewrite_an_already_correct_map(self):
        keyboard.configure()
        self.commands.clear()
        keyboard.configure(login=True)
        self.assertFalse(any(args == ('xmodmap', '-') or args[:2] == ('gsettings', 'set')
                             for args, _ in self.commands))

    def test_watcher_recovers_late_reset_and_stops_on_restore(self):
        keyboard.configure(function_keys=['F17'])
        original = keyboard.BACKUP.read_text()
        ticks = []

        def tick(seconds):
            ticks.append(seconds)
            if len(ticks) == 1:
                # GNOME resets XKB after the first successful login application.
                self.maps['66'] = ['Caps_Lock', 'NoSymbol', 'Caps_Lock']
                self.locks = ['Caps_Lock']
                self.switch = "'Shift+space'"
            else:
                self.assertEqual(self.maps['66'], ['Hangul', 'NoSymbol', 'Hangul'])
                self.assertEqual(self.locks, [])
                self.assertEqual(self.switch, "'Shift+space,Hangul,F17'")
                self.assertEqual(keyboard.BACKUP.read_text(), original)
                keyboard.configure(restore=True)

        with patch.object(keyboard.time, 'sleep', side_effect=tick):
            keyboard.watch_login()
        self.assertEqual(ticks, [2, 2])
        self.assertEqual(self.maps['66'], ['Caps_Lock', 'NoSymbol', 'Caps_Lock'])
        self.assertFalse(keyboard.BACKUP.exists())

    def test_watcher_preserves_custom_map_and_stops_for_custom_autostart(self):
        keyboard.configure()
        self.maps['66'] = ['Escape']
        self.switch = "'F12'"
        with patch.object(keyboard.time, 'sleep',
                          side_effect=lambda _: keyboard.AUTOSTART.write_text('user change')):
            keyboard.watch_login()
        self.assertEqual(self.maps['66'], ['Escape'])
        self.assertEqual(self.switch, "'F12'")

    def test_watcher_retries_transient_failure_and_bounds_permanent_failure(self):
        keyboard.configure()
        with patch.object(keyboard, 'configure', side_effect=[OSError('not ready'), None]), \
                patch.object(keyboard.time, 'sleep') as sleep:
            # End the loop after the successful second iteration.
            sleep.side_effect = lambda _: keyboard.AUTOSTART.unlink() if sleep.call_count == 2 else None
            keyboard.watch_login()
            self.assertEqual(sleep.call_count, 2)
        keyboard.AUTOSTART.write_text(keyboard.DESKTOP)
        with patch.object(keyboard, 'configure', side_effect=OSError('disconnected')) as apply, \
                patch.object(keyboard.time, 'sleep'), self.assertRaisesRegex(RuntimeError, '세션'):
            keyboard.watch_login()
        self.assertEqual(apply.call_count, 30)

    def test_watcher_skips_wayland_and_duplicate_instance(self):
        keyboard.configure()
        self.commands.clear()
        with patch.object(keyboard.desktop_env, 'x11', return_value=False):
            keyboard.watch_login()
        with patch.object(keyboard.fcntl, 'flock', side_effect=BlockingIOError):
            keyboard.watch_login()
        self.assertEqual(self.commands, [])


class NimfTests(FakeSession, unittest.TestCase):
    """nimf stores the switch keys as two GSettings string arrays, not one string."""

    method = keyboard.NIMF

    def shortcuts(self):
        return [json.loads(self.nimf[key].replace("'", '"')) for key in keyboard.NIMF_SHORTCUTS]

    def test_setup_adds_toggle_to_both_shortcut_lists_and_restores(self):
        self.nimf['shortcuts-to-sys'] = "['Hangul', 'Escape']"
        keyboard.configure(function_keys=['F9'])
        self.assertEqual(self.maps['66'], ['Hangul', 'NoSymbol', 'Hangul'])
        self.assertEqual(self.shortcuts(), [['Hangul', 'F9'], ['Hangul', 'Escape', 'F9']])
        self.assertIn('nimf', keyboard.status())
        self.assertIn('F9', keyboard.status())
        keyboard.configure(function_keys=[])
        self.assertEqual(self.shortcuts(), [['Hangul'], ['Hangul', 'Escape']])
        keyboard.configure(restore=True)
        self.assertEqual(self.shortcuts(), [['Hangul'], ['Hangul', 'Escape']])
        self.assertEqual(self.maps['66'], ['Caps_Lock', 'NoSymbol', 'Caps_Lock'])

    def test_login_reapplies_reset_shortcuts(self):
        keyboard.configure(function_keys=['F9'])
        self.nimf = {'shortcuts-to-lang': "['Hangul']", 'shortcuts-to-sys': "['Hangul']"}
        keyboard.configure(login=True)
        self.assertEqual(self.shortcuts(), [['Hangul', 'F9'], ['Hangul', 'F9']])
        self.nimf['shortcuts-to-lang'] = "['F12']"
        keyboard.configure(login=True)
        self.assertEqual(self.nimf['shortcuts-to-lang'], "['F12']")

    def test_empty_shortcut_list_round_trips(self):
        self.nimf['shortcuts-to-lang'] = '@as []'
        keyboard.configure()
        self.assertEqual(self.shortcuts(), [['Hangul'], ['Hangul']])
        keyboard.configure(restore=True)
        self.assertEqual(self.nimf['shortcuts-to-lang'], '@as []')

    def test_function_keys_above_f12_are_rejected_without_mutation(self):
        keyboard.configure(function_keys=['F12'])
        original = keyboard.BACKUP.read_text()
        self.commands.clear()
        with self.assertRaisesRegex(ValueError, 'F12'):
            keyboard.configure(function_keys=['F13'])
        self.assertEqual(self.commands, [])
        self.assertEqual(keyboard.BACKUP.read_text(), original)

    def test_status_detects_a_toggle_broken_on_one_side_only(self):
        keyboard.configure()
        self.nimf['shortcuts-to-sys'] = '@as []'
        self.assertIn('설정 확인 필요', keyboard.status())


class MethodDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(keyboard, 'BACKUP', Path(self.temp.name) / 'backup.json')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.schemas = set(keyboard.SCHEMAS.values())
        self.running = set()
        patcher = patch.object(keyboard, 'installed_schemas', lambda: self.schemas)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(keyboard, 'running_processes', lambda: self.running)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_single_installed_method_wins(self):
        for method in (keyboard.NIMF, keyboard.IBUS):
            with self.subTest(method=method):
                self.schemas = {keyboard.SCHEMAS[method]}
                self.assertEqual(keyboard.detect_method(), method)

    def test_running_process_breaks_the_tie_before_the_environment(self):
        self.running = {'nimf', 'systemd'}
        with patch.dict(os.environ, {'GTK_IM_MODULE': 'ibus', 'QT_IM_MODULE': '', 'XMODIFIERS': ''}):
            self.assertEqual(keyboard.detect_method(), keyboard.NIMF)

    def test_daemon_name_with_a_suffix_still_matches(self):
        self.running = {'ibus-daemon', 'ibus-x11'}
        with patch.dict(os.environ, {'GTK_IM_MODULE': '', 'QT_IM_MODULE': '', 'XMODIFIERS': ''}):
            self.assertEqual(keyboard.detect_method(), keyboard.IBUS)

    def test_environment_breaks_the_tie_when_nothing_runs(self):
        with patch.dict(os.environ, {'GTK_IM_MODULE': 'ibus', 'QT_IM_MODULE': '', 'XMODIFIERS': ''}):
            self.assertEqual(keyboard.detect_method(), keyboard.IBUS)

    def test_ambiguous_and_missing_methods_raise(self):
        with patch.dict(os.environ, {'GTK_IM_MODULE': '', 'QT_IM_MODULE': '', 'XMODIFIERS': ''}):
            with self.assertRaises(RuntimeError):
                keyboard.detect_method()
            self.schemas = set()
            with self.assertRaises(RuntimeError):
                keyboard.detect_method()
            self.assertIsNone(keyboard.active_method())
            self.assertEqual(keyboard.supported_function_keys(), keyboard.FUNCTION_KEYS)

    def test_backup_without_a_method_keeps_using_ibus(self):
        keyboard.BACKUP.write_text(json.dumps({'old_switch': "'Shift+space'"}))
        self.assertEqual(keyboard.active_method(), keyboard.IBUS)
        self.assertEqual(keyboard.method_label(), 'IBus')
        self.assertEqual(keyboard.supported_function_keys(), keyboard.FUNCTION_KEYS)

    def test_configured_method_is_reported_without_detection(self):
        keyboard.BACKUP.write_text(json.dumps({'input_method': keyboard.NIMF}))
        self.schemas = set()
        self.assertEqual(keyboard.method_label(), 'nimf')
        self.assertEqual(keyboard.supported_function_keys(), keyboard.FUNCTION_KEYS[:12])
