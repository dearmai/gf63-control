import unittest
import json
import os
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
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


class PlankTests(unittest.TestCase):
    def test_process_selection_excludes_other_users_displays_buses_and_binaries(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'plank'
            binary.touch()
            other = root / 'other'
            other.touch()
            entries = []
            for pid, display, bus, executable, extra in (
                    (10, ':10', 'current', binary, ['--name', 'dock1']),
                    (11, ':11', 'current', binary, []),
                    (12, ':10', 'other', binary, []),
                    (13, ':10', 'current', binary, ['--display=:11']),
                    (14, ':10', 'current', other, []),
                    (16, ':11', 'current', binary, ['--display', ':10'])):
                entry = root / str(pid)
                entry.mkdir()
                (entry / 'exe').symlink_to(executable)
                (entry / 'cmdline').write_bytes(b'\0'.join(os.fsencode(arg) for arg in ['plank'] + extra) + b'\0')
                (entry / 'environ').write_bytes(f'DISPLAY={display}\0DBUS_SESSION_BUS_ADDRESS={bus}\0'.encode())
                entries.append(entry)
            foreign = MagicMock()
            foreign.name = '17'
            foreign.stat.return_value.st_uid = os.getuid() + 1
            entries.append(foreign)
            proc = MagicMock()
            proc.iterdir.return_value = entries
            with patch.object(core, 'Path', side_effect=lambda path: proc if path == '/proc' else Path(path)), \
                    patch.dict(core.os.environ, {'DISPLAY': ':10', 'DBUS_SESSION_BUS_ADDRESS': 'current'}):
                found = core.plank_processes(str(binary))
            self.assertEqual({pid for pid, _ in found}, {10, 16})
            self.assertEqual(found[0][1], [str(binary), '--name', 'dock1'])

    @patch.object(core.subprocess, 'Popen')
    @patch.object(core.os, 'kill')
    @patch.object(core.shutil, 'which', return_value=None)
    @patch.object(core.desktop_env, 'x11', return_value=True)
    @patch.dict(core.os.environ, {'DISPLAY': ':10'})
    def test_missing_plank_does_not_stop_any_process(self, x11, which, kill, launch):
        message, available = core.plank_status()
        self.assertFalse(available)
        self.assertIn('설치되어 있지 않습니다', message)
        with self.assertRaisesRegex(RuntimeError, '설치되어 있지 않습니다'):
            core.restart_plank()
        kill.assert_not_called()
        launch.assert_not_called()

    def test_restart_waits_for_exit_and_preserves_custom_dock_arguments(self):
        command = ['/bin/plank', '--name', 'dock2']
        child = MagicMock()
        child.poll.return_value = None
        with patch.object(core, 'plank_status', return_value=('', True)), \
                patch.object(core.shutil, 'which', return_value='/bin/plank'), \
                patch.object(core, 'plank_processes', side_effect=[[(10, command)], [(10, command)], [], [(20, command)]]), \
                patch.object(core.os, 'kill') as kill, \
                patch.object(core.time, 'sleep'), \
                patch.object(core.subprocess, 'Popen', return_value=child) as launch:
            message, available = core.restart_plank()
        self.assertTrue(available)
        self.assertIn('다시 시작했습니다', message)
        kill.assert_called_once_with(10, core.signal.SIGTERM)
        self.assertEqual(launch.call_args.args, (command,))
        self.assertTrue(launch.call_args.kwargs['start_new_session'])
        self.assertNotIn('shell', launch.call_args.kwargs)

    def test_failed_stop_does_not_start_a_duplicate_dock(self):
        with patch.object(core, 'plank_status', return_value=('', True)), \
                patch.object(core.shutil, 'which', return_value='/bin/plank'), \
                patch.object(core, 'plank_processes', return_value=[(10, ['/bin/plank'])]), \
                patch.object(core.os, 'kill'), \
                patch.object(core.time, 'monotonic', side_effect=[0, 6]), \
                patch.object(core.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(RuntimeError, '종료되지 않아'):
                core.restart_plank()
        launch.assert_not_called()

    def test_early_launch_failure_is_not_reported_as_success(self):
        child = MagicMock()
        child.poll.return_value = 1
        with patch.object(core, 'plank_status', return_value=('', True)), \
                patch.object(core.shutil, 'which', return_value='/bin/plank'), \
                patch.object(core, 'plank_processes', side_effect=[[], [], []]), \
                patch.object(core.time, 'sleep'), \
                patch.object(core.subprocess, 'Popen', return_value=child):
            with self.assertRaisesRegex(RuntimeError, '실행을 확인하지 못했습니다'):
                core.restart_plank()


if __name__ == '__main__':
    unittest.main()
