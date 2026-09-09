import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import configure_lid
import gf63_core
import gf63_helper
import gf63_lid


class LidTests(unittest.TestCase):
    def test_panel_closes_reopens_and_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = Path(tmp) / 'bl_power'
            panel.write_text('0')
            with patch.object(gf63_lid, 'PANEL', panel):
                control = gf63_lid.Panel()
                control.update(True)
                self.assertEqual(panel.read_text().strip(), '4')
                control.update(True)
                control.update(False)
                self.assertEqual(panel.read_text().strip(), '0')
                control.update(True)
                control.restore()
                self.assertEqual(panel.read_text().strip(), '0')

    def test_panel_preserves_external_change_and_initial_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = Path(tmp) / 'bl_power'
            panel.write_text('4')
            with patch.object(gf63_lid, 'PANEL', panel):
                control = gf63_lid.Panel()
                control.update(True)
                control.update(False)
                self.assertEqual(panel.read_text().strip(), '4')
                panel.write_text('0')
                control.update(True)
                panel.write_text('1')
                control.restore()
                self.assertEqual(panel.read_text(), '1')

    def test_lid_parser_rejects_missing_ambiguous_and_invalid_sensor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(gf63_lid, 'LIDS', root):
                with self.assertRaises(RuntimeError):
                    gf63_lid.lid_closed()
                (root / 'LID0').mkdir()
                state = root / 'LID0/state'
                for value, expected in [('state: open\n', False), ('state:  closed\n', True)]:
                    state.write_text(value)
                    self.assertEqual(gf63_lid.lid_closed(), expected)
                state.write_text('unknown')
                with self.assertRaises(RuntimeError):
                    gf63_lid.lid_closed()
                (root / 'LID1').mkdir()
                (root / 'LID1/state').write_text('state: open')
                with self.assertRaises(RuntimeError):
                    gf63_lid.lid_closed()

    @patch('gf63_helper.lid_systemctl')
    def test_helper_rejects_untrusted_value_before_mutation(self, call):
        for value in ['enable', '--now', 'on\nExecStart=bad', '', None]:
            with self.assertRaises(ValueError):
                gf63_helper.set_lid(value)
        call.assert_not_called()

    @patch('gf63_helper.lid_systemctl')
    def test_helper_failure_restores_service_state(self, call):
        call.side_effect = ['disabled', 'inactive', RuntimeError('start failed'), '', '']
        with self.assertRaisesRegex(RuntimeError, 'start failed'):
            gf63_helper.set_lid('on')
        self.assertEqual(call.call_args_list[-2].args, ('disable',))
        self.assertEqual(call.call_args_list[-1].args, ('stop',))

    def test_xfce_conditional_restore_and_repeated_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = [None]
            def write(value):
                state[0] = value
            with patch.object(configure_lid, 'BACKUP', Path(tmp) / 'backup.json'), \
                 patch.object(configure_lid, 'current', side_effect=lambda: state[0]), \
                 patch.object(configure_lid, 'write', side_effect=write):
                configure_lid.configure()
                configure_lid.configure()
                configure_lid.configure(restore=True)
                self.assertIsNone(state[0])
                configure_lid.configure()
                state[0] = 'false'
                configure_lid.configure(restore=True)
                self.assertEqual(state[0], 'false')

    @patch('gf63_core.run', side_effect=RuntimeError('authorization failed'))
    def test_action_failure_restores_xfce(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(configure_lid, 'BACKUP', Path(tmp) / 'backup.json'), \
                 patch.object(configure_lid, 'current', return_value='false'), \
                 patch.object(configure_lid, 'configure'), patch.object(configure_lid, 'write') as write:
                with self.assertRaisesRegex(RuntimeError, 'authorization failed'):
                    gf63_core.apply('lid', 'on')
                write.assert_called_once_with('false')


if __name__ == '__main__':
    unittest.main()
