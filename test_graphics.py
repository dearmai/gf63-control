import unittest
from unittest.mock import patch

import install_graphics as graphics

LSPCI = '''00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT1 [UHD Graphics] [8086:46a3] (rev 0c)
\tDeviceName: Onboard - Video
\tSubsystem: Micro-Star International Co., Ltd. [MSI] Alder Lake-P GT1 [8086:46a3]
\tKernel driver in use: i915
00:14.0 USB controller [0c03]: Intel Corporation Alder Lake PCH USB [8086:51ed]
\tKernel driver in use: xhci_hcd
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation AD107M [GeForce RTX 4050 Max-Q / Mobile] [10de:28a1] (rev a1)
\tSubsystem: Micro-Star International Co., Ltd. [MSI] AD107M [10de:28a1]
\tKernel driver in use: nouveau
01:00.1 Audio device [0403]: NVIDIA Corporation AD107 High Definition Audio [10de:22be]
\tKernel driver in use: snd_hda_intel
'''

DEVICES = '''== /sys/devices/pci0000:00/0000:00:01.0/0000:01:00.0 ==
modalias : pci:v000010DEd000028A1sv00001462sd000013B6bc03sc00i00
vendor   : NVIDIA Corporation
driver   : nvidia-driver-580 - distro non-free
driver   : nvidia-driver-595-open - distro non-free recommended
driver   : xserver-xorg-video-nouveau - distro free builtin
'''


class GraphicsTests(unittest.TestCase):
    def setUp(self):
        self.outputs = {
            ('lspci', '-nnk'): LSPCI,
            ('ubuntu-drivers', 'devices'): DEVICES,
            ('mokutil', '--sb-state'): 'SecureBoot disabled\n',
            ('uname', '-r'): '6.8.0-139-generic\n',
            ('prime-select', 'query'): 'on-demand\n',
        }
        self.tools = {'apt-get', 'dpkg', 'lspci', 'ubuntu-drivers', 'mokutil',
                      'uname', 'prime-select', 'gnome-terminal'}
        patcher = patch.object(graphics, 'run', side_effect=self.run_command)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(graphics.shutil, 'which',
                               side_effect=lambda name: '/usr/bin/' + name if name in self.tools else None)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(graphics, 'kernel_headers', return_value=True)
        self.headers = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(graphics.subprocess, 'Popen')
        self.popen = patcher.start()
        self.addCleanup(patcher.stop)

    def run_command(self, *args, timeout=30):
        if args[0] not in self.tools:
            return None
        return self.outputs.get(args, None)

    def test_card_picks_the_discrete_display_not_its_audio_function(self):
        found = graphics.card()
        self.assertIn('AD107M', found['name'])
        self.assertEqual(found['driver'], 'nouveau')
        self.assertEqual(graphics.model(found), 'GeForce RTX 4050 Max-Q / Mobile')

    def test_status_reports_nouveau_and_the_recommended_package(self):
        text = graphics.status()
        self.assertIn('GeForce RTX 4050 Max-Q / Mobile', text)
        self.assertIn('nouveau', text)
        self.assertIn('nvidia-driver-595-open', text)
        self.assertIn('MOK 등록 불필요', text)
        self.assertIn('6.8.0-139-generic 있음', text)
        self.assertIn('on-demand', text)

    def test_status_asks_for_a_reboot_while_the_package_is_not_yet_bound(self):
        self.outputs[('dpkg-query', '-W', '-f', '${Package} ${Version} ${Status}\n',
                      'nvidia-driver-*')] = 'nvidia-driver-595-open 595.91.07 install ok installed\n'
        self.tools.add('dpkg-query')
        self.assertIn('재부팅이 필요합니다', graphics.status())

    def test_status_reports_the_running_driver_once_bound(self):
        self.outputs[('lspci', '-nnk')] = LSPCI.replace('use: nouveau', 'use: nvidia')
        self.outputs[('nvidia-smi', '--query-gpu=driver_version',
                      '--format=csv,noheader')] = '595.91.07\n'
        self.tools.add('nvidia-smi')
        text = graphics.status()
        self.assertIn('현재 드라이버 · nvidia 595.91.07', text)
        self.assertNotIn('재부팅이 필요합니다', text)

    def test_enabled_secure_boot_warns_about_mok_enrolment(self):
        self.outputs[('mokutil', '--sb-state')] = 'SecureBoot enabled\n'
        self.assertIn('MOK 등록 화면', graphics.status())
        del self.outputs[('mokutil', '--sb-state')]
        self.assertIn('Secure Boot · 상태 확인 불가', graphics.status())

    def test_missing_headers_are_reported_and_block_the_install(self):
        self.headers.return_value = False
        self.assertIn('linux-headers 설치가 필요합니다', graphics.status())
        with self.assertRaisesRegex(RuntimeError, 'linux-headers'):
            graphics.install()
        self.popen.assert_not_called()

    def test_commands_and_script_use_the_recommended_package(self):
        self.assertEqual(graphics.commands(), [
            'sudo apt update', 'sudo apt install nvidia-driver-595-open',
            'sudo prime-select on-demand', 'sudo reboot'])
        text = graphics.script()
        self.assertIn('sudo apt install nvidia-driver-595-open', text)
        self.assertIn('command -v prime-select', text)
        # Never unattended and never an automatic reboot.
        self.assertNotIn(' -y', text)
        self.assertNotIn('reboot', text)

    def test_only_distribution_driver_packages_are_accepted(self):
        for package in ['nvidia-driver-595; rm -rf /', 'nvidia-driver-', 'nouveau',
                        'nvidia-driver-595-open evil', '../nvidia-driver-595']:
            with self.subTest(package=package), self.assertRaises(ValueError):
                graphics.commands(package)
        self.assertIn('nvidia-driver-580-server-open', graphics.commands('nvidia-driver-580-server-open')[1])

    def test_unknown_prime_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            graphics.commands(None, 'turbo')
        self.assertIn('sudo prime-select nvidia', graphics.commands(None, 'nvidia'))

    def test_missing_recommendation_does_not_guess_a_package(self):
        del self.outputs[('ubuntu-drivers', 'devices')]
        self.assertIn('확인 실패', graphics.status())
        with self.assertRaisesRegex(RuntimeError, '드라이버 패키지'):
            graphics.commands()

    def test_install_opens_a_terminal_with_a_fixed_argument_list(self):
        message = graphics.install()
        self.assertIn('터미널', message)
        argv = self.popen.call_args.args[0]
        self.assertEqual(argv[:4], ['/usr/bin/gnome-terminal', '--', 'bash', '-c'])
        self.assertIn('sudo apt install nvidia-driver-595-open', argv[4])
        self.assertEqual(len(argv), 5)

    def test_install_without_a_terminal_reports_instead_of_failing(self):
        self.tools.discard('gnome-terminal')
        self.assertIsNone(graphics.terminal())
        with self.assertRaisesRegex(RuntimeError, '터미널'):
            graphics.install()
        self.popen.assert_not_called()

    def test_non_apt_distribution_is_reported_unavailable(self):
        self.tools.discard('apt-get')
        self.assertIn('apt 계열', graphics.status())
        with self.assertRaisesRegex(RuntimeError, 'apt 계열'):
            graphics.install()
        self.popen.assert_not_called()

    def test_machine_without_an_nvidia_card_is_reported_unavailable(self):
        self.outputs[('lspci', '-nnk')] = LSPCI.split('01:00.0')[0]
        self.assertIn('찾지 못했습니다', graphics.status())
        with self.assertRaisesRegex(RuntimeError, '찾지 못했습니다'):
            graphics.install()
        self.popen.assert_not_called()
