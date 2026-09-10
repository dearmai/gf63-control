import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import configure_mac as config
import mac_shortcut as shortcut


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        # These tests exercise XFCE settings, independently of the host desktop.
        for name, value in [('kind', 'xfce'), ('x11', True)]:
            patcher = patch.object(config.desktop_env, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.values = {'/commands/custom/override': 'true', '/xfwm4/custom/override': 'true',
                       '/xfwm4/custom/<Super>Tab': 'switch_window_key',
                       '/commands/custom/<Super>F10': '/usr/bin/gf63-control',
                       '/xfwm4/custom/<Alt>Tab': 'cycle_windows_key'}
        self.before = dict(self.values)
        for name, value in [('BACKUP', Path(self.temp.name) / 'backup.json')]:
            patcher = patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(config, 'run', return_value='xdotool 3')
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(config, 'properties', side_effect=lambda: dict(self.values))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(config, 'write', side_effect=self.write)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, prop, value):
        if value is None:
            self.values.pop(prop, None)
        else:
            self.values[prop] = value

    def test_apply_repeat_restore_preserves_original_bindings(self):
        self.assertIn('13/13', config.configure())
        backup = config.BACKUP.read_text()
        config.configure()
        self.assertEqual(config.BACKUP.read_text(), backup)
        self.assertEqual(self.values['/commands/custom/<Super>F10'], '/usr/bin/gf63-control')
        self.assertEqual(self.values['/xfwm4/custom/<Alt>Tab'], 'cycle_windows_key')
        config.configure(restore=True)
        self.assertEqual(self.values, self.before)
        self.assertFalse(config.BACKUP.exists())

    def test_conflicting_cross_provider_and_modifier_order_preserved(self):
        self.values['/xfwm4/custom/<Super>c'] = 'custom_action'
        self.values['/commands/custom/<Super><Shift>z'] = 'user-command'
        result = config.configure()
        self.assertIn('11/13', result)
        self.assertNotIn('/commands/custom/<Super>c', self.values)
        self.assertNotIn('/commands/custom/<Shift><Super>z', self.values)
        self.assertEqual(self.values['/commands/custom/<Super><Shift>z'], 'user-command')

    def test_user_changes_survive_reapply_and_restore(self):
        config.configure()
        self.values['/commands/custom/<Super>c'] = 'user-copy'
        del self.values['/commands/custom/<Super>v']
        config.configure()
        config.configure(restore=True)
        self.assertEqual(self.values['/commands/custom/<Super>c'], 'user-copy')
        self.assertNotIn('/commands/custom/<Super>v', self.values)

    def test_mid_apply_failure_rolls_back_mutations(self):
        count = [0]
        def failing(prop, value):
            count[0] += 1
            if count[0] == 3:
                raise RuntimeError('write failed')
            self.write(prop, value)
        with patch.object(config, 'write', side_effect=failing):
            with self.assertRaisesRegex(RuntimeError, 'write failed'):
                config.configure()
        self.assertEqual(self.values, self.before)
        self.assertFalse(config.BACKUP.exists())

    def test_restore_failure_keeps_pending_backup(self):
        config.configure()
        with patch.object(config, 'write', side_effect=RuntimeError('restore failed')):
            with self.assertRaises(RuntimeError):
                config.configure(restore=True)
        self.assertTrue(config.BACKUP.exists())
        config.configure(restore=True)
        self.assertEqual(self.values, self.before)

    def test_inactive_provider_is_not_overridden(self):
        self.values['/xfwm4/custom/override'] = 'false'
        with self.assertRaises(RuntimeError):
            config.configure()
        self.assertFalse(config.BACKUP.exists())

    def test_terminal_preference_persists_and_rejects_invalid_modes(self):
        with patch.object(config, 'OPTIONS', Path(self.temp.name) / 'options.json'):
            self.assertEqual(config.terminal_mode(), 'clipboard')
            config.set_terminal_mode('disabled')
            self.assertEqual(config.terminal_mode(), 'disabled')
            with self.assertRaises(ValueError):
                config.set_terminal_mode('unknown')
            self.assertEqual(config.terminal_mode(), 'disabled')



class DispatchTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(config, 'terminal_mode', return_value='clipboard')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_terminal_disabled_mode_preserves_general_apps(self):
        for action, expected in shortcut.GENERAL.items():
            self.assertIsNone(shortcut.sequence(action, 'Xfce4-terminal', 'disabled'))
            self.assertEqual(shortcut.sequence(action, 'Firefox', 'disabled'), expected)
        with self.assertRaises(ValueError):
            shortcut.sequence('copy', 'XTerm', 'arbitrary')


    def test_terminal_uses_clipboard_not_interrupt_or_shell_control(self):
        self.assertEqual(shortcut.sequence('copy', 'Xfce4-terminal'), 'ctrl+shift+c')
        self.assertEqual(shortcut.sequence('paste', 'XTerm'), 'ctrl+shift+v')
        self.assertEqual(shortcut.sequence('copy', 'Firefox'), 'ctrl+c')
        self.assertEqual(shortcut.sequence('select-all', 'Xfce4-terminal'), 'ctrl+shift+a')
        self.assertEqual(shortcut.sequence('find', 'Xfce4-terminal'), 'ctrl+shift+f')
        for action in ('save', 'undo', 'cut'):
            self.assertIsNone(shortcut.sequence(action, 'Xfce4-terminal'))

    @patch.object(shortcut, 'run')
    @patch.object(shortcut, 'locked', return_value=True)
    def test_locked_session_never_injects(self, locked, run):
        shortcut.dispatch('copy')
        run.assert_not_called()

    @patch.object(shortcut, 'locked', return_value=False)
    @patch.object(shortcut, 'run', side_effect=['12', 'Firefox', '13'])
    def test_focus_change_drops_action(self, run, locked):
        shortcut.dispatch('copy')
        self.assertFalse(any(call.args[:2] == ('xdotool', 'key') for call in run.call_args_list))

    @patch.object(shortcut, 'locked', side_effect=[False, True])
    @patch.object(shortcut, 'run', side_effect=['12', 'Firefox'])
    def test_lock_during_dispatch_drops_action(self, run, locked):
        shortcut.dispatch('copy')
        self.assertEqual(run.call_count, 2)

    @patch.object(shortcut, 'locked', return_value=False)
    @patch.object(shortcut, 'run', side_effect=['12', 'Xfce4-terminal', '12', ''])
    def test_terminal_dispatch_uses_clear_modifiers(self, run, locked):
        shortcut.dispatch('paste')
        self.assertEqual(run.call_args.args, ('xdotool', 'key', '--clearmodifiers', '--delay', '0', 'ctrl+shift+v'))

    @patch.object(shortcut, 'run')
    def test_untrusted_action_rejected(self, run):
        with self.assertRaises(ValueError):
            shortcut.dispatch('paste; command')
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
