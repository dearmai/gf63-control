import unittest
import json
from unittest.mock import patch
from pathlib import Path
import gf63_core as core
import gf63_helper as helper


class HelperTests(unittest.TestCase):
    def test_power_presets(self):
        quiet = helper.power_config('quiet')
        self.assertEqual(quiet['max'], 60)
        self.assertFalse(quiet['turbo'])
        self.assertIn('no_turbo=1', helper.profile_text(quiet))

    def test_power_rejects_arbitrary_configuration(self):
        valid = helper.power_config('balanced')
        for field, value in [('max', 0), ('max', True), ('max', 101), ('turbo', 'yes'),
                             ('epp', 'power\n[script]\nscript=bad'), ('fan', 'advanced'),
                             ('mode', '../../bad'), ('boost', 1)]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    helper.power_config(json.dumps(dict(valid, **{field: value})))
        with self.assertRaises(ValueError):
            helper.power_config(json.dumps(dict(valid, script='bad')))

    def test_invalid_actions_and_values(self):
        for action, value in [('battery', '9'), ('battery', '101'), ('brightness', '0'),
                              ('brightness', '101'), ('keyboard', '-1'), ('keyboard', '4'),
                              ('webcam', 'toggle'), ('cooler_boost', '1'),
                              ('../../etc/passwd', 'x'), ('battery', '60;id')]:
            with self.subTest(action=action, value=value):
                with self.assertRaises(ValueError):
                    helper.resolve(action, value)

    def test_keyboard_fixed_path(self):
        path, value = helper.resolve('keyboard', '2')
        self.assertEqual(str(path), '/sys/class/leds/msiacpi::kbd_backlight/brightness')
        self.assertEqual(value, '2')

    @patch.object(Path, 'read_text', return_value='96000')
    def test_brightness_scaling(self, _):
        self.assertEqual(helper.resolve('brightness', '5')[1], '4800')

    @patch.object(Path, 'glob', return_value=[])
    def test_missing_battery_rejected(self, _):
        with self.assertRaises(ValueError):
            helper.resolve('battery', '60')

    @patch.object(Path, 'glob', return_value=[Path('one'), Path('two')])
    def test_ambiguous_battery_rejected(self, _):
        with self.assertRaises(ValueError):
            helper.resolve('battery', '60')


class DesktopTests(unittest.TestCase):
    def test_volume_parse(self):
        self.assertEqual(core.parse_volume('Volume: 0.45 [MUTED]'), (45, True))
        self.assertEqual(core.parse_volume('Volume: 1.00'), (100, False))
        with self.assertRaises(ValueError):
            core.parse_volume('Could not connect to PipeWire')

    @patch('gf63_core.run', return_value='↳ USB Mouse id=4\n↳ Elantech Touchpad id=19\n↳ OTHER Touchpad id=23')
    def test_only_touchpads_selected(self, _):
        self.assertEqual(core.touchpads(), ['19', '23'])

    @patch('gf63_core.snapshot', return_value={'brightness': 100})
    @patch('gf63_core.run')
    def test_brightness_clamped(self, command, _):
        core.apply('brightness-up')
        command.assert_called_once_with('pkexec', core.HELPER, 'brightness', '100')

    @patch('gf63_core.snapshot', return_value={})
    @patch('gf63_core.run')
    def test_volume_capped(self, command, _):
        core.apply('volume-up')
        command.assert_called_once_with('wpctl', 'set-volume', '-l', '1.0', '@DEFAULT_AUDIO_SINK@', '5%+')

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            core.apply('shell')


if __name__ == '__main__':
    unittest.main()
