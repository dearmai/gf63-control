import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import battery_limit as app


class BatteryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.battery = self.root / 'BAT1'
        self.battery.mkdir()
        for name, value in {'type': 'Battery', 'capacity': '58',
                            'status': 'Not charging', app.END: '60', app.START: '50'}.items():
            (self.battery / name).write_text(value)

    def test_ignores_peripheral_battery(self):
        mouse = self.root / 'mouse'
        mouse.mkdir()
        for name, value in {'type': 'Battery', 'capacity': '90', 'scope': 'Device'}.items():
            (mouse / name).write_text(value)
        self.assertEqual(app.select_battery(self.root), self.battery)

    def test_rejects_invalid_values_without_write(self):
        for value in (-1, 0, 9, 101, 256):
            with self.assertRaises(app.ControlError):
                app.set_limit(self.battery, value)
        self.assertEqual(app.read(self.battery / app.END), '60')

    @patch('battery_limit.os.geteuid', return_value=1000)
    def test_unprivileged_write_rejected(self, _):
        with self.assertRaises(app.ControlError):
            app.set_limit(self.battery, 80)
        self.assertEqual(app.read(self.battery / app.END), '60')

    @patch('battery_limit.os.geteuid', return_value=0)
    def test_write_and_verify(self, _):
        self.assertTrue(app.set_limit(self.battery, 80))
        self.assertEqual(app.read(self.battery / app.END), '80')
        self.assertFalse(app.set_limit(self.battery, 80))

    def test_missing_driver_does_not_create_interface(self):
        (self.battery / app.END).unlink()
        with self.assertRaises(app.ControlError):
            app.set_limit(self.battery, 80)
        self.assertFalse((self.battery / app.END).exists())

    @patch('battery_limit.os.geteuid', return_value=0)
    def test_readback_mismatch_reported(self, _):
        with patch.object(Path, 'write_text', return_value=3):
            with self.assertRaisesRegex(app.ControlError, '검증 실패'):
                app.set_limit(self.battery, 80)

    def test_ambiguous_batteries_require_selection(self):
        other = self.root / 'BAT2'
        other.mkdir()
        for name in ('type', 'capacity', app.END):
            (other / name).write_text(app.read(self.battery / name))
        with self.assertRaises(app.ControlError):
            app.select_battery(self.root)
        self.assertEqual(app.select_battery(self.root, 'BAT1'), self.battery)


if __name__ == '__main__':
    unittest.main()
