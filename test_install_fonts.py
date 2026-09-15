import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import install_fonts as installer


class InstallFontTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        source = root / 'source'
        source.mkdir()
        files = {'font.otf': b'font test fixture', 'LICENSE.txt': b'OFL test fixture'}
        for name, data in files.items():
            (source / name).write_bytes(data)
        (source / 'SHA256.json').write_text(json.dumps({n: hashlib.sha256(d).hexdigest() for n,d in files.items()}))
        for patcher in (patch.object(installer, 'RESOURCES', source),
                        patch.object(installer, 'DESTINATION', root / 'user/fonts/gf63-control')):
            patcher.start()
            self.addCleanup(patcher.stop)

    @patch.object(installer.subprocess, 'run')
    def test_install_license_and_idempotence(self, run):
        installer.install()
        self.assertEqual((installer.DESTINATION / 'LICENSE.txt').read_bytes(), b'OFL test fixture')
        installer.install()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs['timeout'], 30)

    @patch.object(installer.subprocess, 'run')
    def test_corrupt_bundle_rejected_before_writing(self, run):
        (installer.RESOURCES / 'font.otf').write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, '무결성'):
            installer.install()
        self.assertFalse(installer.DESTINATION.exists())
        run.assert_not_called()

    @patch.object(installer.subprocess, 'run')
    def test_user_changes_survive(self, run):
        installer.install()
        file = installer.DESTINATION / 'font.otf'
        file.write_bytes(b'user font')
        with self.assertRaisesRegex(RuntimeError, '사용자'):
            installer.install()
        self.assertEqual(file.read_bytes(), b'user font')

    @patch.object(installer.subprocess, 'run', side_effect=subprocess.TimeoutExpired('fc-cache', 30))
    def test_cache_failure_removes_new_install(self, run):
        with self.assertRaises(subprocess.TimeoutExpired):
            installer.install()
        self.assertFalse(installer.DESTINATION.exists())
        self.assertEqual(list(installer.DESTINATION.parent.iterdir()), [])

    def test_manifest_cannot_escape_resources(self):
        (installer.RESOURCES / 'SHA256.json').write_text(json.dumps({'../outside.ttf': '0' * 64}))
        with self.assertRaises(ValueError):
            installer.install()
        self.assertFalse(installer.DESTINATION.exists())

    def add_ligature(self):
        name = 'd2coding/ligature.ttf'
        path = installer.RESOURCES / name
        path.parent.mkdir()
        path.write_bytes(b'ligature fixture')
        manifest = installer.RESOURCES / 'SHA256.json'
        files = json.loads(manifest.read_text())
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(files))
        return installer.DESTINATION / name

    @patch.object(installer.subprocess, 'run')
    def test_existing_install_gains_ligature_and_preserves_extra_files(self, run):
        installer.install()
        extra = installer.DESTINATION / 'personal.ttf'
        extra.write_bytes(b'personal')
        target = self.add_ligature()
        installer.install()
        self.assertEqual(target.read_bytes(), b'ligature fixture')
        self.assertEqual(extra.read_bytes(), b'personal')
        installer.install()
        self.assertEqual(run.call_count, 2)

    @patch.object(installer.subprocess, 'run')
    def test_failed_upgrade_restores_existing_install(self, run):
        installer.install()
        before = {str(p.relative_to(installer.DESTINATION)): p.read_bytes()
                  for p in installer.DESTINATION.rglob('*') if p.is_file()}
        target = self.add_ligature()
        run.side_effect = subprocess.TimeoutExpired('fc-cache', 30)
        with self.assertRaises(subprocess.TimeoutExpired):
            installer.install()
        self.assertFalse(target.parent.exists())
        self.assertEqual(before, {str(p.relative_to(installer.DESTINATION)): p.read_bytes()
                                 for p in installer.DESTINATION.rglob('*') if p.is_file()})

    @patch.object(installer.subprocess, 'run')
    def test_upgrade_rejects_symlink_directory(self, run):
        installer.install()
        target = self.add_ligature()
        target.parent.symlink_to(installer.RESOURCES / 'd2coding', target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, '사용자'):
            installer.install()
        self.assertEqual(run.call_count, 1)


class BundledFontTests(unittest.TestCase):
    def test_shipped_fonts_and_licenses_match_manifest(self):
        files = installer.contents()
        self.assertEqual(sum(name.endswith('.otf') for name in files), 9)
        self.assertEqual(sum(name.endswith('.ttf') for name in files), 4)
        self.assertEqual(sum(name.endswith('-ligature.ttf') for name in files), 2)
        self.assertIn('pretendard/LICENSE.txt', files)
        self.assertIn('d2coding/OFL.txt', files)


if __name__ == '__main__':
    unittest.main()
