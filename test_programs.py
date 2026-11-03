import io
import os
import struct
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import install_programs as programs


def icon_executable(pe64=True):
    """Small PE fixture with one 1x1 icon and a normal resource hierarchy."""
    bitmap = struct.pack('<IiiHHIIiiII', 40, 1, 2, 1, 32, 0, 4, 0, 0, 0, 0)
    bitmap += b'\x00\xff\xff\xff' + b'\0' * 4
    group = struct.pack('<HHHBBBBHHIH', 0, 1, 1, 1, 1, 0, 0, 1, 32, len(bitmap), 7)
    resources = bytearray()

    def allocate(size):
        offset = len(resources)
        resources.extend(b'\0' * size)
        return offset

    def directory(items):
        offset = allocate(16 + len(items) * 8)
        struct.pack_into('<H', resources, offset + 14, len(items))
        for index, (identifier, value) in enumerate(items.items()):
            if isinstance(value, dict):
                entry = directory(value) | 0x80000000
            else:
                entry = allocate(16)
                payload = allocate(len(value))
                resources[payload:payload + len(value)] = value
                struct.pack_into('<IIII', resources, entry, 0x1000 + payload, len(value), 0, 0)
            struct.pack_into('<II', resources, offset + 16 + index * 8, identifier, entry)
        return offset

    directory({3: {7: {1033: bitmap}}, 14: {1: {1033: group}}})
    data = bytearray(0x200)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<H', data, 0x86, 1)
    optional_size = 240 if pe64 else 224
    struct.pack_into('<H', data, 0x94, optional_size)
    struct.pack_into('<H', data, 0x98, 0x20b if pe64 else 0x10b)
    directories = 0x98 + (112 if pe64 else 96)
    struct.pack_into('<I', data, directories - 4, 16)
    struct.pack_into('<II', data, directories + 16, 0x1000, len(resources))
    struct.pack_into('<IIII', data, 0x98 + optional_size + 8,
                     len(resources), 0x1000, len(resources), 0x200)
    return bytes(data + resources), bitmap


class ExecutableIconTests(unittest.TestCase):
    def test_extracts_pe32_and_pe64_icon_without_executing(self):
        for pe64 in (False, True):
            data, bitmap = icon_executable(pe64)
            result = programs.executable_icon(data)
            self.assertEqual(result[:6], struct.pack('<HHH', 0, 1, 1))
            self.assertEqual(struct.unpack_from('<II', result, 14), (len(bitmap), 22))
            self.assertEqual(result[22:], bitmap)

    def test_invalid_or_truncated_executable_is_rejected(self):
        data, _ = icon_executable()
        for invalid in (b'', b'MZ', b'not an executable', data[:100], data[:-1]):
            with self.subTest(size=len(invalid)), self.assertRaises(ValueError):
                programs.executable_icon(invalid)

    def test_cyclic_resource_directory_is_rejected(self):
        data = bytearray(icon_executable()[0])
        # Point the icon group's language entry back to the resource root.
        group_type = struct.unpack_from('<I', data, 0x200 + 28)[0] & 0x7fffffff
        group_name = struct.unpack_from('<I', data, 0x200 + group_type + 20)[0] & 0x7fffffff
        struct.pack_into('<I', data, 0x200 + group_name + 20, 0x80000000)
        with self.assertRaisesRegex(ValueError, '계층'):
            programs.executable_icon(data)


class ProgramOutputTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.log = Path(temporary.name) / 'install/install.log'
        log_patch = patch.object(programs, 'LOG', self.log)
        log_patch.start()
        self.addCleanup(log_patch.stop)

    def command(self, stdout, stderr=b'', code=0):
        return [sys.executable, '-c',
                'import os; os.write(1, {!r}); os.write(2, {!r}); '
                'raise SystemExit({})'.format(stdout, stderr, code)]

    def test_non_utf8_output_does_not_abort_success_and_is_logged(self):
        output = b'done \xc0\nFontSmoothingType    REG_DWORD    0x2\n'
        error = '완료\n'.encode('utf-8')
        result = programs.run(self.command(output, error))
        self.assertIn('FontSmoothingType    REG_DWORD    0x2', result)
        self.assertEqual(result, output.decode('utf-8', errors='replace').strip())
        self.assertEqual(self.log.read_text(encoding='utf-8'),
                         output.decode('utf-8', errors='replace') + '완료\n')

    def test_non_utf8_failure_still_reports_command_error_and_logs_output(self):
        for stdout, stderr in [(b'', b'failed \xc0'), (b'failed \xc0', b'')]:
            with self.subTest(stderr=stderr):
                with self.assertRaisesRegex(RuntimeError, 'failed'):
                    programs.run(self.command(stdout, stderr, code=1))
        self.assertEqual(self.log.read_text(encoding='utf-8'), 'failed �failed �')

    def test_timeout_is_preserved(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            programs.run([sys.executable, '-c', 'import time; time.sleep(10)'],
                         timeout=0.1)

    def test_runtime_check_does_not_decode_unused_output(self):
        real_run = subprocess.run
        for code in (0, 1):
            with self.subTest(code=code):
                def execute(args, **kwargs):
                    self.assertEqual(args, ['flatpak', 'info', '--user', programs.REF])
                    return real_run(self.command(b'info \xc0', b'error \xc0', code), **kwargs)
                with patch.object(programs.shutil, 'which', return_value='/usr/bin/flatpak'), \
                        patch.object(programs.subprocess, 'run', side_effect=execute):
                    self.assertEqual(programs.runtime_installed(), code == 0)


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
                            ('ICON', root / 'icons/hicolor/256x256/apps/gf63-kakaotalk.png'),
                            ('LOG', root / 'data/kakaotalk-install/install.log')]:
            self.mock(name, value)
        self.mock('runtime_installed', return_value=True)
        self.mock('run', return_value='')
        def install_icon():
            programs.ICON.parent.mkdir(parents=True, exist_ok=True)
            programs.ICON.write_bytes(b'icon')
        self.mock('install_icon', side_effect=install_icon)
        p = patch.object(programs.os, 'geteuid', return_value=1000)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(programs.shutil, 'which', return_value='/usr/bin/flatpak')
        p.start(); self.addCleanup(p.stop)
        p = patch.object(programs.install_fonts, 'contents', return_value={'pretendard/Pretendard-Regular.otf': b'font'})
        p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'XMODIFIERS': ''})
        p.start(); self.addCleanup(p.stop)
        p = patch.object(programs.keyboard, 'detect_method', return_value=programs.keyboard.NIMF)
        self.active_method = p.start(); self.addCleanup(p.stop)

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
        self.assertEqual(programs.LAUNCHER.read_text(), programs.desktop_file())
        self.assertIn('@im=nimf', programs.LAUNCHER.read_text())
        self.assertEqual(unrelated.read_text(), 'existing WinApps launcher')
        download.assert_not_called()
        rendering.assert_called_once()
        self.assertFalse(any('/S' in c.args[0] for c in programs.run.call_args_list))

    def test_launcher_is_rewritten_when_the_input_method_changes(self):
        self.installed()
        self.mock('configure_rendering')
        self.mock('configure_text_fonts')
        self.mock('download')
        programs.install()
        self.assertIn('@im=nimf', programs.LAUNCHER.read_text())
        self.active_method.return_value = programs.keyboard.IBUS
        self.assertIn('실행 메뉴를 등록', programs.status())
        programs.install()
        self.assertIn('@im=ibus', programs.LAUNCHER.read_text())
        self.assertIn('설치됨 ·', programs.status())

    def test_legacy_gear_icon_is_migrated_without_reinstalling(self):
        self.installed()
        self.mock('configure_rendering')
        self.mock('configure_text_fonts')
        download = self.mock('download')
        programs.LAUNCHER.parent.mkdir(parents=True)
        for method in programs.keyboard.LABELS:
            legacy = programs.DESKTOP.format(module=method).replace(
                'Icon=gf63-kakaotalk\n', 'Icon=gf63-control\n')
            programs.LAUNCHER.write_text(legacy)
            self.assertIn('실행 메뉴를 등록', programs.status())
            programs.install()
            self.assertIn('Icon=gf63-kakaotalk\n', programs.LAUNCHER.read_text())
            self.assertTrue(programs.ICON.is_file())
        download.assert_not_called()

    def test_missing_icon_requests_repair(self):
        self.installed()
        programs.LAUNCHER.parent.mkdir(parents=True)
        programs.LAUNCHER.write_text(programs.desktop_file())
        self.assertIn('실행 메뉴를 등록', programs.status())

    def test_icon_failure_preserves_existing_launcher(self):
        self.installed()
        self.mock('configure_rendering')
        self.mock('configure_text_fonts')
        programs.LAUNCHER.parent.mkdir(parents=True)
        legacy = programs.desktop_file().replace('Icon=gf63-kakaotalk\n', 'Icon=gf63-control\n')
        programs.LAUNCHER.write_text(legacy)
        self.mock('install_icon', side_effect=RuntimeError('아이콘 등록 실패'))
        with self.assertRaisesRegex(RuntimeError, '아이콘 등록 실패'):
            programs.install()
        self.assertEqual(programs.LAUNCHER.read_text(), legacy)

    def test_undetected_input_method_falls_back_to_ibus(self):
        self.active_method.side_effect = RuntimeError('입력기 없음')
        self.assertEqual(programs.im_module(), programs.keyboard.IBUS)
        self.assertIn('--env=XMODIFIERS=@im=ibus', programs.wine('x.exe'))

    def test_session_xim_takes_priority_over_old_keyboard_backup(self):
        with patch.dict(os.environ, {'XMODIFIERS': '@im=nimf'}), \
                patch.object(programs.keyboard, 'active_method', return_value=programs.keyboard.IBUS):
            self.active_method.return_value = programs.keyboard.IBUS
            self.assertEqual(programs.im_module(), programs.keyboard.NIMF)
            self.assertIn('--env=XMODIFIERS=@im=nimf', programs.wine('x.exe'))
            self.assertIn('--env=XMODIFIERS=@im=nimf', programs.desktop_file())
            self.active_method.assert_not_called()

    def test_live_detection_does_not_use_backup_when_xim_is_unset(self):
        with patch.object(programs.keyboard, 'active_method', return_value=programs.keyboard.IBUS):
            self.assertEqual(programs.im_module(), programs.keyboard.NIMF)
            self.active_method.assert_called_once()

    def test_a_customized_launcher_is_still_preserved(self):
        self.installed()
        programs.LAUNCHER.parent.mkdir(parents=True)
        programs.LAUNCHER.write_text(programs.desktop_file() + 'Hidden=true\n')
        with self.assertRaisesRegex(RuntimeError, '변경'):
            programs.install()

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
