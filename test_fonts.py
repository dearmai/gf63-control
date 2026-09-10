from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import os
from unittest.mock import patch

import configure_fonts as fonts


class FontTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        patcher = patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE', 'XDG_SESSION_DESKTOP': 'KDE'})
        patcher.start()
        self.addCleanup(patcher.stop)
        for name, value in [('CONFIG', root / 'config'), ('DATA', root / 'data'),
                            ('AUTOSTART', root / 'fonts.desktop'), ('BACKUP', root / 'backup.json')]:
            patcher = patch.object(fonts, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.values = {('kdeglobals', 'General', 'font'): 'Noto Sans,12,-1,5,50,0,0,0,0,0,Regular',
                       ('konsolerc', 'Desktop Entry', 'DefaultProfile'): 'Personal.profile'}
        self.before = dict(self.values)
        for target, name, kwargs in [
            (fonts.desktop_env, 'kind', dict(return_value='kde')),
            (fonts, 'families', dict(return_value={'Pretendard', 'D2Coding'})),
            (fonts, 'read_key', dict(side_effect=self.read_key)),
            (fonts, 'write_key', dict(side_effect=self.write_key)),
        ]:
            patcher = patch.object(target, name, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def read_key(self, file, group, key):
        return self.values.get((Path(file).name, group, key))

    def write_key(self, file, group, key, value):
        if Path(file).name == fonts.PROFILE_NAME:
            with open(file, 'a') as output:
                output.write(f'[{group}]\n{key}={value}\n')
            return
        identity = (Path(file).name, group, key)
        if value is None:
            self.values.pop(identity, None)
        else:
            self.values[identity] = value

    def test_apply_repeat_restore_preserves_size_and_parent(self):
        self.assertIn('8/8', fonts.configure())
        self.assertEqual(self.values[('kdeglobals', 'General', 'font')],
                         'Pretendard,12,-1,5,50,0,0,0,0,0')
        profile = fonts.DATA / 'konsole' / fonts.PROFILE_NAME
        self.assertIn('Parent=Personal.profile', profile.read_text())
        self.assertIn('Font=D2Coding,11,', profile.read_text())
        backup = fonts.BACKUP.read_text()
        fonts.configure()
        self.assertEqual(fonts.BACKUP.read_text(), backup)
        fonts.configure(restore=True)
        self.assertEqual(self.values, self.before)
        self.assertFalse(profile.exists())
        self.assertFalse(fonts.BACKUP.exists())

    def test_missing_font_does_not_mutate(self):
        with patch.object(fonts, 'families', return_value={'D2Coding', 'Sans'}):
            with self.assertRaisesRegex(RuntimeError, 'Pretendard'):
                fonts.configure()
        self.assertEqual(self.values, self.before)
        self.assertFalse(fonts.BACKUP.exists())

    def test_variable_pretendard_and_absent_default_profile(self):
        self.values.pop(('konsolerc', 'Desktop Entry', 'DefaultProfile'))
        with patch.object(fonts, 'families', return_value={'Pretendard Variable', 'D2Coding'}):
            fonts.configure()
        self.assertTrue(self.values[('kdeglobals', 'General', 'font')].startswith('Pretendard Variable,'))
        self.assertNotIn('Parent=', (fonts.DATA / 'konsole' / fonts.PROFILE_NAME).read_text())
        fonts.configure(restore=True)
        self.assertNotIn(('konsolerc', 'Desktop Entry', 'DefaultProfile'), self.values)

    def test_custom_settings_and_profile_survive_restore(self):
        fonts.configure()
        identity = ('kdeglobals', 'General', 'font')
        self.values[identity] = 'User Font,15,-1,5,50,0,0,0,0,0'
        profile = fonts.DATA / 'konsole' / fonts.PROFILE_NAME
        profile.write_text(profile.read_text() + '\n# user customization\n')
        fonts.configure()
        fonts.configure(restore=True)
        self.assertEqual(self.values[identity], 'User Font,15,-1,5,50,0,0,0,0,0')
        self.assertTrue(profile.exists())

    def test_existing_profile_is_not_overwritten(self):
        profile = fonts.DATA / 'konsole' / fonts.PROFILE_NAME
        profile.parent.mkdir(parents=True)
        profile.write_text('user data')
        with self.assertRaisesRegex(RuntimeError, '이미'):
            fonts.configure()
        self.assertEqual(profile.read_text(), 'user data')
        self.assertEqual(self.values, self.before)

    def test_failure_rolls_back_including_new_profile(self):
        original = fonts.write
        def fail(item, value):
            if item.get('key') == 'DefaultProfile' and value == fonts.PROFILE_NAME:
                raise RuntimeError('write failed')
            original(item, value)
        with patch.object(fonts, 'write', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'write failed'):
                fonts.configure()
        self.assertEqual(self.values, self.before)
        self.assertFalse((fonts.DATA / 'konsole' / fonts.PROFILE_NAME).exists())
        self.assertFalse(fonts.BACKUP.exists())

    def test_failed_restore_keeps_backup_for_retry(self):
        fonts.configure()
        with patch.object(fonts, 'write', side_effect=RuntimeError('readback failed')):
            with self.assertRaises(RuntimeError):
                fonts.configure(restore=True)
        self.assertTrue(fonts.BACKUP.exists())
        fonts.configure(restore=True)
        self.assertEqual(self.values, self.before)

    def test_font_detection_does_not_accept_substitution(self):
        with patch.object(fonts, 'families', wraps=FontTests.original_families), \
             patch.object(fonts, 'run', return_value='Pretendard,Pretendard SemiBold\nD2Coding\n'):
            self.assertEqual(fonts.families(), {'Pretendard', 'Pretendard SemiBold', 'D2Coding'})

    original_families = staticmethod(fonts.families)

    def test_non_kde_apply_is_rejected(self):
        with patch.object(fonts.desktop_env, 'kind', return_value='xfce'):
            with self.assertRaisesRegex(RuntimeError, 'KDE'):
                fonts.configure()
        self.assertFalse(fonts.BACKUP.exists())


class GnomeFontTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.values = {}
        self.defaults = {key: 'Sans Bold 12' if key == 'titlebar-font' else 'Sans 11'
                         for _, key in fonts.GNOME_KEYS}
        self.locked = set()
        for patcher in (
            patch.object(fonts, 'GNOME_BACKUP', Path(self.tmp.name) / 'gnome.json'),
            patch.object(fonts, 'AUTOSTART', Path(self.tmp.name) / 'autostart/fonts.desktop'),
            patch.object(fonts, 'BACKUP', Path(self.tmp.name) / 'kde.json'),
            patch.object(fonts, 'environment', return_value='gnome'),
            patch.object(fonts, 'families', return_value={'Pretendard', 'D2Coding'}),
            patch.object(fonts, 'gnome_access', side_effect=self.access),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def access(self, operation, item, value=None):
        key = item['key']
        if operation == 'write':
            if key in self.locked:
                raise RuntimeError('locked')
            if value is None:
                self.values.pop(key, None)
            else:
                self.values[key] = value
        effective = self.values.get(key, self.defaults[key])
        result = dict(old=self.values.get(key), effective=effective, writable=key not in self.locked)
        if operation == 'plan':
            result['installed'] = value + ' ' + effective.split(' ', 1)[1]
        return result

    def test_apply_repeat_restore_resets_inherited_defaults(self):
        self.values['font-name'] = 'Personal 13'
        self.assertIn('4/4', fonts.configure())
        self.assertEqual(self.values['font-name'], 'Pretendard 13')
        self.assertEqual(self.values['titlebar-font'], 'Pretendard Bold 12')
        self.assertEqual(self.values['monospace-font-name'], 'D2Coding 11')
        self.assertFalse(fonts.BACKUP.exists())
        before = fonts.GNOME_BACKUP.read_text()
        fonts.configure()
        self.assertEqual(fonts.GNOME_BACKUP.read_text(), before)
        fonts.configure(restore=True)
        self.assertEqual(self.values, {'font-name': 'Personal 13'})

    def test_custom_font_survives_repeat_and_restore(self):
        fonts.configure()
        self.values['font-name'] = 'Custom 15'
        self.assertIn('3/4', fonts.configure())
        fonts.configure(restore=True)
        self.assertEqual(self.values, {'font-name': 'Custom 15'})

    def test_locked_key_prevents_all_mutation(self):
        self.locked.add('monospace-font-name')
        with self.assertRaisesRegex(RuntimeError, '잠근'):
            fonts.configure()
        self.assertEqual(self.values, {})
        self.assertFalse(fonts.GNOME_BACKUP.exists())

    def test_partial_failure_rolls_back(self):
        original = fonts.write
        def fail(item, value):
            if item['key'] == 'titlebar-font' and value is not None:
                raise RuntimeError('failed')
            original(item, value)
        with patch.object(fonts, 'write', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                fonts.configure()
        self.assertEqual(self.values, {})
        self.assertFalse(fonts.GNOME_BACKUP.exists())

    def test_missing_font_does_not_mutate(self):
        with patch.object(fonts, 'families', return_value={'Pretendard'}):
            with self.assertRaisesRegex(RuntimeError, 'D2Coding'):
                fonts.configure()
        self.assertEqual(self.values, {})

    def test_startup_apply_login_and_restore(self):
        with patch('install_fonts.install', return_value='설치 완료') as install:
            fonts.enable_startup()
            self.assertTrue(fonts.startup_enabled())
            self.assertIn('OnlyShowIn=GNOME;', fonts.AUTOSTART.read_text())
            self.values['font-name'] = 'Custom 15'
            fonts.login()
            self.assertEqual(self.values['font-name'], 'Custom 15')
            self.assertEqual(install.call_count, 2)
        fonts.configure(restore=True)
        self.assertFalse(fonts.AUTOSTART.exists())
        self.assertEqual(self.values, {'font-name': 'Custom 15'})

    def test_startup_conflict_and_disabled_login(self):
        fonts.AUTOSTART.parent.mkdir(parents=True)
        fonts.AUTOSTART.write_text('user file')
        with patch('install_fonts.install') as install:
            with self.assertRaisesRegex(RuntimeError, '사용자'):
                fonts.enable_startup()
            fonts.disable_startup()
            fonts.login()
            install.assert_not_called()
        self.assertEqual(fonts.AUTOSTART.read_text(), 'user file')

    def test_failed_install_does_not_enable_startup_or_apply(self):
        with patch('install_fonts.install', side_effect=RuntimeError('checksum failed')):
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                fonts.enable_startup()
        self.assertFalse(fonts.AUTOSTART.exists())
        self.assertEqual(self.values, {})

    def test_disable_startup_keeps_applied_fonts(self):
        with patch('install_fonts.install', return_value='installed'):
            fonts.enable_startup()
        expected = dict(self.values)
        fonts.disable_startup()
        self.assertEqual(self.values, expected)
        self.assertFalse(fonts.startup_enabled())



class FontEnvironmentTests(unittest.TestCase):
    def test_gnome_variants_and_wayland(self):
        for name in ('GNOME', 'GNOME-Classic:GNOME', 'ubuntu:GNOME'):
            with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': name, 'XDG_SESSION_TYPE': 'wayland'}):
                self.assertEqual(fonts.environment(), 'gnome')


if __name__ == '__main__':
    unittest.main()
