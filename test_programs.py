import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import install_programs as programs


class ProgramTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.root = root
        for name, value in [('DATA', root / 'data'), ('PREFIX', root / 'prefix'),
                            ('EXE', root / 'prefix/KakaoTalk.exe'),
                            ('APPLICATIONS', root / 'applications'),
                            ('LAUNCHER', root / 'applications/gf63-kakaotalk-wine.desktop'),
                            ('LOG', root / 'data/kakaotalk-install/install.log')]:
            self.mock(name, value)
        self.mock('runtime_installed', return_value=True)
        self.mock('run', return_value='')
        p = patch.object(programs.os, 'geteuid', return_value=1000)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(programs.shutil, 'which', return_value='/usr/bin/flatpak')
        p.start(); self.addCleanup(p.stop)
        p = patch.object(programs.install_fonts, 'contents', return_value={'pretendard/Pretendard-Regular.otf': b'font'})
        p.start(); self.addCleanup(p.stop)

    def mock(self, name, *args, **kwargs):
        p = patch.object(programs, name, *args, **kwargs)
        result = p.start(); self.addCleanup(p.stop)
        return result

    def installed(self):
        programs.EXE.parent.mkdir(parents=True)
        programs.EXE.write_bytes(b'MZapplication')

    def test_existing_install_repairs_menu_without_downloading_or_reinstalling(self):
        self.installed()
        rendering = self.mock('configure_rendering')
        self.mock('configure_text_fonts')
        download = self.mock('download')
        unrelated = programs.APPLICATIONS / 'kakaotalk.desktop'
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text('existing WinApps launcher')
        self.assertIn('설치됨', programs.install())
        self.assertEqual(programs.LAUNCHER.read_text(), programs.DESKTOP)
        self.assertEqual(unrelated.read_text(), 'existing WinApps launcher')
        download.assert_not_called()
        rendering.assert_called_once()
        self.assertFalse(any('/S' in c.args[0] for c in programs.run.call_args_list))

    def test_custom_launcher_is_preserved_before_mutation(self):
        programs.LAUNCHER.parent.mkdir(parents=True)
        programs.LAUNCHER.write_text('custom launcher')
        with self.assertRaisesRegex(RuntimeError, '변경'):
            programs.install()
        programs.run.assert_not_called()
        self.assertEqual(programs.LAUNCHER.read_text(), 'custom launcher')

    def test_installer_exit_success_without_executable_is_failure(self):
        self.mock('download')
        with self.assertRaisesRegex(RuntimeError, '실행 파일'):
            programs.install()
        self.assertFalse(programs.LAUNCHER.exists())

    def test_flatpak_failure_does_not_download_or_create_launcher(self):
        self.mock('runtime_installed', return_value=False)
        self.mock('run', side_effect=RuntimeError('network failed'))
        download = self.mock('download')
        with self.assertRaisesRegex(RuntimeError, 'network failed'):
            programs.install()
        download.assert_not_called()
        self.assertFalse(programs.LAUNCHER.exists())

    def test_root_and_missing_flatpak_are_rejected(self):
        with patch.object(programs.os, 'geteuid', return_value=0), self.assertRaises(RuntimeError):
            programs.install()
        with patch.object(programs.shutil, 'which', return_value=None), self.assertRaises(RuntimeError):
            programs.install()
        programs.run.assert_not_called()

    def test_concurrent_installer_is_rejected(self):
        with patch.object(programs.fcntl, 'flock', side_effect=BlockingIOError), self.assertRaisesRegex(RuntimeError, '진행 중'):
            programs.install()
        programs.run.assert_not_called()

    def download_response(self, data, length=None):
        response = io.BytesIO(data)
        response.headers = {'Content-Length': str(length if length is not None else len(data))}
        p = patch.object(programs.urllib.request, 'build_opener')
        opener = p.start(); self.addCleanup(p.stop)
        opener.return_value.open.return_value = response

    def test_download_is_atomic_and_validates_length_and_executable(self):
        target = programs.DATA / 'kakaotalk-install/KakaoTalk_Setup.exe'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'MZprevious')
        for payload, size in [(b'MZpartial', 500), (b'<html>error</html>', None)]:
            self.download_response(payload, size)
            with self.assertRaisesRegex(RuntimeError, '다운로드'):
                programs.download(lambda _: None)
            self.assertEqual(target.read_bytes(), b'MZprevious')
            self.assertFalse(target.with_suffix('.part').exists())
        self.download_response(b'MZcomplete')
        self.assertEqual(programs.download(lambda _: None).read_bytes(), b'MZcomplete')

    def test_untrusted_redirect_is_rejected(self):
        handler = programs.OfficialRedirect()
        for url in ('http://lk.kakaocdn.net/a', 'https://example.com/a', 'https://lk.kakaocdn.net.example.com/a'):
            with self.assertRaises(RuntimeError):
                handler.redirect_request(None, None, 302, '', {}, url)

    def test_launch_requires_installation_and_reports_nonzero_exit(self):
        with self.assertRaisesRegex(RuntimeError, '먼저 설치'):
            programs.launch()
        self.installed()
        with patch.object(programs.subprocess, 'Popen') as spawn:
            spawn.return_value.wait.return_value = 1
            with self.assertRaisesRegex(RuntimeError, '실행 실패'):
                programs.launch()

    def test_wine_prefix_and_command_are_fixed(self):
        args = programs.wine('reg', 'query', 'HKCU')
        self.assertIn('--env=WINEPREFIX=/var/data/kakaotalk', args)
        self.assertIn('--command=wine', args)
        self.assertNotIn('sudo', args)
        self.assertNotIn('pkexec', args)

    def test_rendering_readback_mismatch_is_reported(self):
        programs.LOG.parent.mkdir(parents=True)
        backup = programs.LOG.parent / 'font-rendering-before.reg'
        backup.write_text('original settings')
        self.mock('run', side_effect=['', 'FontSmoothing    REG_SZ    0'])
        with self.assertRaisesRegex(RuntimeError, '확인 실패'):
            programs.configure_rendering()
        self.assertEqual(backup.read_text(), 'original settings')

    def test_text_fonts_preserve_backup_and_do_not_replace_symbols(self):
        programs.LOG.parent.mkdir(parents=True)
        backup = programs.LOG.parent / 'font-substitutes-before.reg'
        backup.write_text('original mappings')
        def execute(args, **unused):
            if args[-2:] == ['/var/data/kakaotalk-install/text-fonts-readback.reg', '/y']:
                source = programs.LOG.parent / 'text-fonts.reg'
                (programs.LOG.parent / 'text-fonts-readback.reg').write_bytes(source.read_bytes())
            return ''
        self.mock('run', side_effect=execute)
        programs.configure_text_fonts()
        self.assertEqual(backup.read_text(), 'original mappings')
        result = (programs.LOG.parent / 'text-fonts.reg').read_text(encoding='utf-16')
        self.assertIn('"맑은 고딕"="Pretendard"', result)
        self.assertIn('"MS Sans Serif"="Pretendard"', result)
        for symbol in ('Wingdings', 'Symbol', 'Segoe UI Emoji', 'Segoe MDL2 Assets'):
            self.assertNotIn('"' + symbol + '"=', result)

    def test_text_font_readback_failure_is_not_reported_as_success(self):
        def execute(args, **unused):
            if args[-2:] == ['/var/data/kakaotalk-install/text-fonts-readback.reg', '/y']:
                (programs.LOG.parent / 'text-fonts-readback.reg').write_text('missing values', encoding='utf-16')
            return ''
        self.mock('run', side_effect=execute)
        with self.assertRaisesRegex(RuntimeError, '대체 글꼴 확인 실패'):
            programs.configure_text_fonts()

    def test_font_only_repair_does_not_install_or_rewrite_launcher(self):
        self.installed()
        programs.LAUNCHER.parent.mkdir(parents=True)
        programs.LAUNCHER.write_text('custom menu')
        text_fonts = self.mock('configure_text_fonts')
        rendering = self.mock('configure_rendering')
        self.assertIn('완전히 종료', programs.repair_fonts())
        text_fonts.assert_called_once()
        rendering.assert_called_once()
        programs.run.assert_not_called()
        self.assertEqual(programs.LAUNCHER.read_text(), 'custom menu')

    def test_font_repair_requires_install_and_respects_install_lock(self):
        with self.assertRaisesRegex(RuntimeError, '먼저 설치'):
            programs.repair_fonts()
        self.installed()
        with patch.object(programs.fcntl, 'flock', side_effect=BlockingIOError), self.assertRaisesRegex(RuntimeError, '진행 중'):
            programs.repair_fonts()
        programs.run.assert_not_called()

    def test_wine_settings_uses_kakao_prefix_and_reports_failure(self):
        with self.assertRaisesRegex(RuntimeError, '먼저 설치'):
            programs.open_wine_settings()
        self.installed()
        with patch.object(programs.subprocess, 'Popen') as spawn:
            spawn.return_value.wait.return_value = 1
            with self.assertRaisesRegex(RuntimeError, '실행 실패'):
                programs.open_wine_settings()
            self.assertIn('--env=WINEPREFIX=/var/data/kakaotalk', spawn.call_args.args[0])
            self.assertEqual(spawn.call_args.args[0][-1], 'winecfg.exe')
