"""Startup contracts without opening PIA, installing packages or changing login."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from src import launcher
from src.instance import InstanceLock
from src.config_paths import IMAGES_DIR, SOUNDS_DIR, sound_path

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_os_lock_prevents_duplicates_and_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pia.lock'
            first, second = InstanceLock(path), InstanceLock(path)
            try:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                first.close()
                self.assertTrue(second.acquire())
            finally:
                first.close()
                second.close()

    def test_background_launch_detaches_and_logs(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(launcher, 'BASE_DIR', Path(directory)), patch.object(launcher.subprocess, 'Popen') as spawn, patch.object(launcher.time, 'sleep'):
            spawn.return_value.poll.return_value = None
            launcher.start_background()
            args, options = spawn.call_args
            self.assertEqual(args[0][-3:], ['-m', 'src.launcher', '--foreground'])
            self.assertEqual(options['stdin'], subprocess.DEVNULL)
            self.assertEqual(options['stderr'], subprocess.STDOUT)
            self.assertTrue((Path(directory) / 'logs/launcher.log').exists())
            if os.name == 'nt':
                self.assertTrue(options['creationflags'] & subprocess.CREATE_NO_WINDOW)
            else:
                self.assertTrue(options['start_new_session'])

    def test_already_running_does_not_spawn(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(launcher, 'BASE_DIR', Path(directory)), patch.object(launcher.subprocess, 'Popen') as spawn:
            lock = InstanceLock(Path(directory) / 'data/pia.lock')
            self.assertTrue(lock.acquire())
            try:
                launcher.start_background()
                spawn.assert_not_called()
            finally:
                lock.close()

    def test_assets_and_legacy_sound_paths(self):
        self.assertTrue((IMAGES_DIR / 'pia.svg').is_file())
        self.assertTrue((IMAGES_DIR / 'pia.png').is_file())
        self.assertTrue((SOUNDS_DIR / 'start.mp3').is_file())
        self.assertEqual(sound_path('sounds/start.mp3', 'start.mp3'), SOUNDS_DIR / 'start.mp3')
        self.assertEqual(sound_path('../sounds/start.mp3', 'start.mp3'), SOUNDS_DIR / 'start.mp3')
        self.assertEqual(sound_path(str(ROOT / 'sounds/start.mp3'), 'start.mp3'), SOUNDS_DIR / 'start.mp3')
        self.assertFalse(list(ROOT.glob('*.py')))
        self.assertFalse(list(ROOT.glob('*.png')))


class ShellStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name == 'nt':
            from src.autostart import git_bash
            cls.bash = str(git_bash())
        else:
            cls.bash = shutil.which('bash')
        if not cls.bash:
            raise unittest.SkipTest('Bash não disponível')

    def script(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/usr/bin/env bash\n' + text + '\n', encoding='utf-8', newline='\n')
        path.chmod(0o755)

    def test_installer_starts_after_preparation_and_can_opt_out(self):
        with tempfile.TemporaryDirectory(prefix='pia installation ') as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / 'install.sh', root / 'install.sh')
            log = root / 'calls.log'
            self.script(root / 'bin/uv', 'printf "uv:%s\\n" "$*" >> "$TEST_LOG"')
            self.script(root / 'start.sh', 'printf "start\\n" >> "$TEST_LOG"')
            env = dict(os.environ, PIA_TEST_BIN=str(root / 'bin'), PIA_TEST_INSTALL=str(root / 'install.sh'), TEST_LOG=str(log))
            base = 'if command -v cygpath >/dev/null; then PIA_TEST_BIN="$(cygpath -u "$PIA_TEST_BIN")"; fi; export PATH="$PIA_TEST_BIN:$PATH"; export OSTYPE=linux-gnu; bash "$PIA_TEST_INSTALL" --no-system --no-autostart'
            result = subprocess.run([self.bash, '-c', base], env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text()
            self.assertIn('uv:sync --python 3.12 --extra podcast', calls)
            self.assertTrue(calls.rstrip().endswith('start'))
            log.unlink()
            result = subprocess.run([self.bash, '-c', base + ' --no-start'], env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('start', log.read_text().splitlines())

    def test_start_uses_installed_python_and_project_cwd(self):
        with tempfile.TemporaryDirectory(prefix='pia start ') as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / 'start.sh', root / 'start.sh')
            self.script(root / '.venv/bin/python', 'printf "python:%s\\n" "$*"; pwd')
            result = subprocess.run([self.bash, str(root / 'start.sh'), '--dry-run'], env=dict(os.environ, OSTYPE='linux-gnu'), capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('python:-m src.launcher --dry-run', result.stdout)
            self.assertIn(root.name, result.stdout)

    def test_shell_syntax(self):
        for name in ('start.sh', 'install.sh'):
            result = subprocess.run([self.bash, '-n', str(ROOT / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
