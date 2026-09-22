import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import configure_cinnamon as cinnamon

OTHER = 'org.cinnamon.desktop.keybindings.wm'


class CaptureShortcutTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(cinnamon, 'BACKUP', Path(self.temp.name) / 'cinnamon.json')
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(cinnamon.desktop_env, 'kind', return_value='cinnamon')
        self.kind = patcher.start()
        self.addCleanup(patcher.stop)
        self.schemas = {cinnamon.SCHEMA, OTHER}
        self.values = {
            (cinnamon.SCHEMA, 'area-screenshot-clip'): "['<Control><Shift>Print']",
            (cinnamon.SCHEMA, 'screenshot-clip'): "['<Control>Print']",
            (OTHER, 'show-desktop'): "['<Super>d']",
        }
        self.commands = []
        patcher = patch.object(cinnamon, 'run', side_effect=self.run_command)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_command(self, *args):
        self.commands.append(args)
        if args == ('gsettings', 'list-schemas'):
            return '\n'.join(sorted(self.schemas))
        if args[:2] == ('gsettings', 'list-keys'):
            return '\n'.join(key for schema, key in self.values if schema == args[2])
        if args[:2] == ('gsettings', 'list-recursively'):
            return '\n'.join('%s %s %s' % (s, k, v) for (s, k), v in self.values.items() if s == args[2])
        if args[:2] == ('gsettings', 'get'):
            return self.values[(args[2], args[3])]
        if args[:2] == ('gsettings', 'set'):
            self.values[(args[2], args[3])] = args[4]
            return ''
        self.fail(str(args))

    def current(self):
        return cinnamon.accelerators(cinnamon.SCHEMA, cinnamon.ACTION)

    def test_apply_then_restore_returns_the_original(self):
        self.assertIn('기본 설정 사용 중', cinnamon.status())
        message = cinnamon.configure('<Super><Shift>s')
        self.assertIn('Super + Shift + S', message)
        self.assertEqual(self.current(), ['<Super><Shift>s'])
        self.assertEqual(cinnamon.selected(), '<Super><Shift>s')
        cinnamon.configure(restore=True)
        self.assertEqual(self.current(), ['<Control><Shift>Print'])
        self.assertFalse(cinnamon.BACKUP.exists())

    def test_reapplying_keeps_the_first_original(self):
        cinnamon.configure('<Super><Shift>s')
        cinnamon.configure('<Super>Print')
        self.assertEqual(json.loads(cinnamon.BACKUP.read_text())['old'], ['<Control><Shift>Print'])
        self.assertEqual(self.current(), ['<Super>Print'])
        cinnamon.configure(restore=True)
        self.assertEqual(self.current(), ['<Control><Shift>Print'])

    def test_only_allowlisted_accelerators_are_written(self):
        for binding in ['<Super>x', '<Super><Shift>s extra', '', None and '', 'Print; rm -rf /']:
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                cinnamon.configure(binding or '<Super>x')
        self.assertFalse(any(args[:2] == ('gsettings', 'set') for args in self.commands))
        self.assertFalse(cinnamon.BACKUP.exists())

    def test_an_accelerator_another_action_uses_is_refused(self):
        self.values[(OTHER, 'show-desktop')] = "['<Super>Print']"
        self.commands.clear()
        with self.assertRaisesRegex(RuntimeError, 'show-desktop'):
            cinnamon.configure('<Super>Print')
        self.assertFalse(any(args[:2] == ('gsettings', 'set') for args in self.commands))
        self.assertFalse(cinnamon.BACKUP.exists())

    def test_the_action_does_not_conflict_with_itself(self):
        self.assertIsNone(cinnamon.holder('<Control><Shift>Print'))
        cinnamon.configure('<Control><Shift>Print')
        self.assertEqual(self.current(), ['<Control><Shift>Print'])

    def test_an_external_change_blocks_apply_and_shows_in_status(self):
        cinnamon.configure('<Super><Shift>s')
        original = cinnamon.BACKUP.read_text()
        self.values[(cinnamon.SCHEMA, cinnamon.ACTION)] = "['<Alt>F12']"
        self.assertIn('설정 확인 필요', cinnamon.status())
        with self.assertRaisesRegex(RuntimeError, '외부에서 변경'):
            cinnamon.configure('<Super>Print')
        self.assertEqual(cinnamon.BACKUP.read_text(), original)
        self.assertEqual(self.current(), ['<Alt>F12'])

    def test_restore_leaves_a_value_the_user_changed_afterwards(self):
        cinnamon.configure('<Super><Shift>s')
        self.values[(cinnamon.SCHEMA, cinnamon.ACTION)] = "['<Alt>F12']"
        cinnamon.configure(restore=True)
        self.assertEqual(self.current(), ['<Alt>F12'])
        self.assertFalse(cinnamon.BACKUP.exists())

    def test_empty_accelerator_list_round_trips(self):
        self.values[(cinnamon.SCHEMA, cinnamon.ACTION)] = '@as []'
        self.assertIn('미설정', cinnamon.status())
        cinnamon.configure('<Super><Shift>s')
        self.assertEqual(self.current(), ['<Super><Shift>s'])
        cinnamon.configure(restore=True)
        self.assertEqual(self.values[(cinnamon.SCHEMA, cinnamon.ACTION)], '@as []')

    def test_other_desktops_report_unavailable_without_touching_gsettings(self):
        for name in ('xfce', 'kde', 'unsupported'):
            with self.subTest(desktop=name):
                self.kind.return_value = name
                self.commands.clear()
                self.assertIn('Cinnamon', cinnamon.status())
                with self.assertRaisesRegex(RuntimeError, 'Cinnamon'):
                    cinnamon.configure('<Super><Shift>s')
                self.assertFalse(any(args[:2] == ('gsettings', 'set') for args in self.commands))

    def test_missing_schema_or_key_is_reported(self):
        self.schemas = set()
        self.assertIn('스키마를 찾을 수 없습니다', cinnamon.status())
        self.schemas = {cinnamon.SCHEMA}
        del self.values[(cinnamon.SCHEMA, cinnamon.ACTION)]
        self.assertIn('항목이 없습니다', cinnamon.status())

    def test_restore_without_a_backup_is_a_no_op(self):
        self.commands.clear()
        self.assertIn('기본 설정 사용 중', cinnamon.configure(restore=True))
        self.assertFalse(any(args[:2] == ('gsettings', 'set') for args in self.commands))

    def test_every_choice_is_allowlisted_and_labelled(self):
        self.assertEqual(len(dict(cinnamon.CHOICES)), len(cinnamon.CHOICES))
        self.assertEqual(cinnamon.BINDINGS, tuple(b for b, _ in cinnamon.CHOICES))
        self.assertIn(cinnamon.DEFAULT, cinnamon.BINDINGS)
        for binding, label in cinnamon.CHOICES:
            self.assertTrue(binding.startswith('<'), binding)
            self.assertTrue(label.strip(), binding)
