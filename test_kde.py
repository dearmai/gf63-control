import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import configure_kde as kde
import configure_kde_lid as lid
import desktop_env
import mac_shortcut


class DesktopTests(unittest.TestCase):
    def test_desktop_and_wayland_detection(self):
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE', 'XDG_SESSION_TYPE': 'x11', 'WAYLAND_DISPLAY': ''}):
            self.assertEqual(desktop_env.kind(), 'kde')
            self.assertEqual(desktop_env.screensaver()[0], 'org.freedesktop.ScreenSaver')
            desktop_env.require_shortcuts()
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE', 'XDG_SESSION_TYPE': 'wayland'}):
            with self.assertRaises(RuntimeError): desktop_env.require_shortcuts()
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'GNOME', 'XDG_SESSION_DESKTOP': 'gnome'}):
            self.assertEqual(desktop_env.kind(), 'unsupported')

    def test_cinnamon_uses_its_own_screensaver_and_keeps_shortcuts_unsupported(self):
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'X-Cinnamon', 'XDG_SESSION_DESKTOP': 'cinnamon',
                                     'XDG_SESSION_TYPE': 'x11', 'WAYLAND_DISPLAY': ''}):
            self.assertEqual(desktop_env.kind(), 'cinnamon')
            self.assertEqual(desktop_env.screensaver(),
                             ('org.cinnamon.ScreenSaver', '/org/cinnamon/ScreenSaver', 'org.cinnamon.ScreenSaver'))
            with self.assertRaises(RuntimeError): desktop_env.require_shortcuts()

    @patch.object(desktop_env, 'call', side_effect=RuntimeError('no locker'))
    def test_unknown_lock_state_blocks_input(self, call):
        self.assertTrue(desktop_env.locked())

    @patch.object(desktop_env, 'x11', return_value=False)
    @patch.object(mac_shortcut, 'run')
    def test_wayland_does_not_inject_xwayland_input(self, run, x11):
        mac_shortcut.dispatch('copy')
        run.assert_not_called()

    def test_konsole_copy_paste_find_do_not_send_shell_signals(self):
        self.assertEqual(mac_shortcut.sequence('copy', 'konsole'), 'ctrl+shift+c')
        self.assertEqual(mac_shortcut.sequence('paste', 'konsole'), 'ctrl+shift+v')
        self.assertEqual(mac_shortcut.sequence('find', 'konsole'), 'ctrl+shift+f')
        self.assertIsNone(mac_shortcut.sequence('select-all', 'konsole'))
        self.assertIsNone(mac_shortcut.sequence('undo', 'konsole'))


class KdeShortcutTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.keys = {('kwin', 'Walk Through Windows'): [0x09000001],
                     ('kwin', 'Walk Through Windows (Reverse)'): [0x0b000001]}
        self.before = dict(self.keys)
        self.conflicts = set()
        for name, value in [('CONFIG', Path(self.temp.name) / 'config'), ('DATA', Path(self.temp.name) / 'data')]:
            patcher = patch.object(kde, name, value)
            patcher.start(); self.addCleanup(patcher.stop)
        for target, kwargs in [(desktop_env, {'require_shortcuts': None}), (desktop_env, {'x11': True})]:
            for name, value in kwargs.items():
                patcher = patch.object(target, name, return_value=value)
                patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(kde, 'call', side_effect=self.call)
        patcher.start(); self.addCleanup(patcher.stop)

    def call(self, method, signature, *values):
        if method == 'shortcut':
            return (self.keys.get(tuple(values[0][:2]), []),)
        if method == 'getGlobalShortcutsByKey':
            return ([],)
        if method == 'isGlobalShortcutAvailable':
            return (values[0] not in self.conflicts,)
        if method == 'doRegister':
            return ()
        if method == 'setShortcut':
            self.assertEqual(values[2], 6)
            self.keys[tuple(values[0][:2])] = list(values[1])
            return (list(values[1]),)
        if method == 'unregister':
            self.keys.pop(tuple(values), None)
            return (True,)
        self.fail(method)

    def test_kde_apply_repeat_and_restore_preserves_alt_tab(self):
        self.assertIn('13/13', kde.configure())
        backup = kde.backup('mac').read_text()
        kde.configure()
        self.assertEqual(kde.backup('mac').read_text(), backup)
        self.assertEqual(self.keys[('kwin', 'Walk Through Windows')][0], 0x09000001)
        kde.configure(restore=True)
        self.assertEqual(self.keys, self.before)
        self.assertFalse(list(kde.DATA.glob('*.desktop')))

    def test_kf6_key_sequence_encoding_preserves_multistroke_shortcuts(self):
        identity = ['kwin', 'Walk Through Windows', 'KWin', 'Windows']
        with patch.object(desktop_env, 'call', return_value=([([123],), ([456, 789],)],)) as remote:
            result = kde.modern_call('setShortcut', '(asaiu)', (identity, [123, [456, 789]], 6))
            self.assertEqual(result, ([123, [456, 789]],))
            self.assertEqual(remote.call_args.args[-3:],
                             ('setShortcutKeys', '(asa(ai)u)', (identity, [([123],), ([456, 789],)], 6)))

    def test_stock_clipboard_binding_is_restored(self):
        key = kde.META | ord('V')
        original_call = self.call
        self.keys[('plasmashell', 'show-on-mouse-pos')] = [key]
        self.conflicts.add(key)
        def service(method, signature, *values):
            if method == 'getGlobalShortcutsByKey':
                return ([('show-on-mouse-pos', 'Clipboard', 'plasmashell', 'Plasma',
                          'default', 'Default', [key], [key])],)
            return original_call(method, signature, *values)
        with patch.object(kde, 'call', side_effect=service):
            kde.configure()
            self.assertEqual(self.keys[('plasmashell', 'show-on-mouse-pos')], [])
            self.assertEqual(self.keys[('gf63-mac-paste.desktop', '_launch')], [key])
            kde.configure(restore=True)
            self.assertEqual(self.keys[('plasmashell', 'show-on-mouse-pos')], [key])

    def test_customized_stock_action_is_not_displaced(self):
        key = kde.META | ord('V')
        with patch.object(kde, 'call', return_value=([('show-on-mouse-pos', 'Clipboard', 'plasmashell',
              'Plasma', 'default', 'Default', [key, 123], [key])],)):
            self.assertIsNone(kde.stock_conflicts('paste', kde.specs()['paste']))

    def test_conflict_is_skipped(self):
        self.conflicts.add(kde.META | ord('C'))
        self.assertIn('12/13', kde.configure())
        self.assertFalse((kde.DATA / 'gf63-mac-copy.desktop').exists())

    def test_user_shortcut_changes_survive_restore(self):
        kde.configure()
        self.keys[('gf63-mac-copy.desktop', '_launch')] = [123]
        kde.configure(restore=True)
        self.assertEqual(self.keys[('gf63-mac-copy.desktop', '_launch')], [123])
        self.assertTrue((kde.DATA / 'gf63-mac-copy.desktop').exists())

    def test_readback_failure_rolls_back_new_desktop_and_bindings(self):
        def fail(identity, keys):
            if identity[0] == 'gf63-mac-paste.desktop':
                raise RuntimeError('registration failed')
            self.call('setShortcut', '(asaiu)', identity, keys, 6)
        with patch.object(kde, 'set_keys', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'registration failed'):
                kde.configure()
        self.assertEqual(self.keys, self.before)
        self.assertFalse(list(kde.DATA.glob('*.desktop')))
        self.assertFalse(kde.backup('mac').exists())

    def test_hardware_shortcuts_are_independent(self):
        self.assertIn('5/5', kde.configure(profile='hardware'))
        self.assertFalse(kde.backup('mac').exists())
        kde.configure(restore=True, profile='hardware')
        self.assertEqual(self.keys, self.before)


class KdeLidTests(unittest.TestCase):
    def test_kde5_and_6_fixed_schema(self):
        with patch('shutil.which', side_effect=lambda name: name if name.endswith('5') else None):
            self.assertEqual(lid.schema(), ('5', 'powermanagementprofilesrc', 'HandleButtonEvents', 'lidAction'))
        with patch('shutil.which', return_value='/usr/bin/kwriteconfig6'):
            self.assertEqual(lid.schema(), ('6', 'powerdevilrc', 'SuspendAndShutdown', 'LidAction'))

    def test_lid_conditional_restore(self):
        with TemporaryDirectory() as tmp:
            values = {'AC': '1', 'Battery': '2', 'LowBattery': lid.MISSING}
            before = dict(values)
            def write(raw):
                values.update({p: '0' for p in lid.PROFILES} if raw == 'true' else json.loads(raw))
            with patch.object(lid, 'BACKUP', Path(tmp) / 'backup.json'), \
                 patch.object(lid, 'values', side_effect=lambda: dict(values)), \
                 patch.object(lid, 'write', side_effect=write):
                lid.configure()
                lid.configure()
                self.assertEqual(lid.current(), 'true')
                values['Battery'] = '8'
                lid.configure(restore=True)
                self.assertEqual(values, dict(before, Battery='8'))
                self.assertFalse(lid.BACKUP.exists())


if __name__ == '__main__':
    unittest.main()
