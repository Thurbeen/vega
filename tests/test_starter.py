"""Exercise distributable assets through the installed Fleet Task API."""
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Starter(unittest.TestCase):
    def test_windows_relative_paths_match_bundle_manifest(self):
        # Exercise the full installation with Windows relative path spelling,
        # even when the host running this regression is POSIX.
        native_relative_to = type(ROOT).relative_to

        def relative_to(path, other, *args, **kwargs):
            result = native_relative_to(path, other, *args, **kwargs)
            if other == ROOT:
                return PureWindowsPath(*result.parts)
            return result

        with patch.object(type(ROOT), 'relative_to', relative_to):
            self.test_clean_workspace_and_task_lifecycle()

    def test_clean_workspace_and_task_lifecycle(self):
        manifest = tomllib.loads((ROOT / 'starter.toml').read_text())
        self.assertEqual(manifest['version'], 1)
        self.assertEqual(manifest['id'], 'vega')
        self.assertEqual(manifest['license'], 'MIT')
        assets = manifest['files']
        self.assertEqual(len(assets), len(set(assets)))
        self.assertIn('LICENSE', assets)
        for asset in assets:
            path = PurePosixPath(asset)
            self.assertFalse(path.is_absolute() or '..' in path.parts)
            self.assertTrue((ROOT / asset).is_file(), asset)
        workspace_assets = {p.relative_to(ROOT).as_posix() for p in (ROOT / 'workspace').rglob('*') if p.is_file()}
        self.assertTrue(workspace_assets <= set(assets))
        fleet = os.environ.get('FLEET_BIN')
        self.assertTrue(fleet, 'Set FLEET_BIN to the Task-only Fleet binary; integration is required')
        # Keep even the throwaway installation outside the system temp partition.
        with tempfile.TemporaryDirectory(prefix='vega-test-', dir=ROOT) as tmp:
            install = Path(tmp)
            workspace = install / 'workspace with spaces'
            for asset in assets:
                target = install / asset
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / asset, target)
            (install / 'workspace').rename(workspace)
            # The emitted production config must parse via Fleet, unchanged.
            config = install / 'config/fleet.toml'
            production = tomllib.loads(config.read_text())
            self.assertEqual(production['runtime']['kind'], 'thurbox')
            self.assertEqual(production['version'], 1)
            def run(*args, cfg=config):
                result = subprocess.run([fleet, '--config', str(cfg), *args], text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return json.loads(result.stdout)
            run('list', 'task', '--json')
            # Only the host transport changes; keep all supported production keys.
            fake = install / 'config/fake.toml'
            runtime = production['runtime']
            runtime['kind'] = 'fake'
            fake.write_text('version = 1\n[data]\ndir = "data"\n[runtime]\n' + '\n'.join(f'{key} = {json.dumps(value)}' for key, value in runtime.items()) + '\ndir = "fake-host"\n')
            tasks = json.loads((install / 'tasks/vega.json').read_text())
            self.assertEqual(len(tasks), 1)
            task = tasks[0]
            self.assertEqual(task['metadata'], {'name': 'vega'})
            self.assertEqual(task['kind'], 'Task')
            self.assertEqual(task['spec']['workspace']['dir'], '{{workspace}}')
            task['spec']['workspace']['dir'] = str(workspace)
            rendered = install / 'vega.json'
            rendered.write_text(json.dumps(tasks))
            run('apply', '-f', str(rendered), '--json', cfg=fake)
            first = run('get', 'task', 'vega', cfg=fake)
            run('reconcile', '--json', cfg=fake)
            briefed = run('get', 'task', 'vega', cfg=fake)
            self.assertEqual(briefed['status']['phase'], 'Briefed')
            self.assertIsNotNone(briefed['status']['brief'])
            run('apply', '-f', str(rendered), '--json', cfg=fake)
            run('reconcile', '--json', cfg=fake)
            repeat = run('get', 'task', 'vega', cfg=fake)
            self.assertEqual(first['metadata']['uid'], repeat['metadata']['uid'])
            self.assertEqual(briefed['status']['session'], repeat['status']['session'])
            self.assertEqual(len(run('list', 'task', '--json', cfg=fake)), 1)
            self.assertTrue((workspace / 'AGENTS.md').is_file())
            for required in ['prompts/mission-control.md', '.agents/skills/task-intake/SKILL.md', '.agents/skills/task-status/SKILL.md']:
                self.assertTrue((workspace / required).is_file())


if __name__ == '__main__':
    unittest.main()
