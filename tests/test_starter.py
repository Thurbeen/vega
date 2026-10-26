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
        self.assertTrue(fleet, 'Set FLEET_BIN to the compatible Fleet binary; integration is required')
        # Keep even the throwaway installation outside the system temp partition.
        with tempfile.TemporaryDirectory(prefix='vega-test-', dir=ROOT) as tmp:
            install = Path(tmp)
            workspace = install / 'workspace with spaces'
            for asset in assets:
                target = install / asset
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / asset, target)
            (install / 'workspace').rename(workspace)
            # Check the instructions a freshly installed Mission Control receives.
            instructions = (workspace / 'AGENTS.md').read_text()
            mission_control = (workspace / 'prompts/mission-control.md').read_text()
            intake = (workspace / '.agents/skills/task-intake/SKILL.md').read_text()
            task_status = (workspace / '.agents/skills/task-status/SKILL.md').read_text()
            task_template = (install / 'tasks/vega.json').read_text()
            for content in [instructions, intake]:
                for rule in ['open every change as a draft',
                             'fleet declare TASK --change-request URL',
                             '<!-- fleet:worker <task uid> -->',
                             'fleet get task TASK']:
                    self.assertIn(rule, content)
            # The installed prompt surface must make Mission Control an
            # orchestration-only role for every substantive kind of request.
            for category in ['design', 'implementation', 'bug fix', 'test',
                             'research', 'review', 'writing', 'operational']:
                self.assertIn(category, mission_control.lower())
            for content in [instructions, mission_control, intake, task_template]:
                self.assertIn('dispatch-only', content.lower())
            for boundary in ['acknowledge', 'clarify', 'status']:
                self.assertIn(boundary, mission_control.lower())
            self.assertIn('without a repository', intake.lower())
            self.assertIn('isolated', intake.lower())
            self.assertIn('do not redo', task_status.lower())
            for content in [intake, task_status]:
                self.assertIn('required by the user or repository', content.lower())
                self.assertIn('draft-only', content.lower())
            # A clean install must let Mission Control coordinate an existing
            # Task session without weakening the dispatch-only boundary. These
            # are documentation contract checks; FakeRuntime does not simulate
            # a live terminal or prove that an agent will obey the guidance.
            direct_guidance = '\n'.join([instructions, mission_control, task_status])
            for contract in [
                'existing owned Task session',
                'status.session',
                'runtime.cli',
                'session capture --lines 0 --json',
                'session send UUID TEXT --json --strict',
                'fleet send TASK TEXT',
                'delivered_via',
                'submitted',
                'queued',
                'working turn',
                'FakeRuntime',
            ]:
                self.assertIn(contract.lower(), direct_guidance.lower())
            self.assertIn('new substantive request', direct_guidance.lower())
            self.assertIn('new task', direct_guidance.lower())
            self.assertIn('--force', direct_guidance)
            # The emitted production config must parse via Fleet, unchanged.
            config = install / 'config/fleet.toml'
            production = tomllib.loads(config.read_text())
            self.assertEqual(production['runtime']['kind'], 'thurbox')
            self.assertEqual(production['version'], 1)
            def run(*args, cfg=config, json_output=True):
                result = subprocess.run([fleet, '--config', str(cfg), *args], text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return json.loads(result.stdout) if json_output else result.stdout
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
            # Execute the optional resource examples shipped in the intake skill.
            examples = []
            for block in intake.split('```json\n')[1:]:
                examples.append(json.loads(block.split('```', 1)[0]))
            self.assertEqual([r['kind'] for r in examples],
                             ['Task', 'EnvProvider', 'TaskConfig', 'Task'])
            provider, defaults, worker = examples[1:]
            worker['spec']['workspace']['dir'] = str(workspace)
            resources = install / 'configured.json'
            resources.write_text(json.dumps([provider, defaults, worker]))
            run('apply', '-f', str(resources), '--json', cfg=fake)
            worker['spec']['dispatch'] = True
            resources.write_text(json.dumps(worker))
            run('apply', '-f', str(resources), '--json', cfg=fake)
            run('reconcile', '--json', cfg=fake)
            name = worker['metadata']['name']
            configured = run('get', 'task', name, cfg=fake)
            self.assertEqual(configured['status']['phase'], 'Briefed')
            self.assertEqual(configured['status']['execution']['harness'], 'codex')
            uid = configured['metadata']['uid']
            snapshot = json.loads((install / f'config/data/launches/{uid}.json').read_text())
            self.assertEqual(snapshot['env']['PROJECT_MODE'], 'focused')
            defaults['spec']['env']['PROJECT_MODE'] = 'changed'
            resources.write_text(json.dumps(defaults))
            run('apply', '-f', str(resources), '--json', cfg=fake)
            run('reconcile', '--json', cfg=fake)
            self.assertEqual(json.loads((install / f'config/data/launches/{uid}.json').read_text()),
                             snapshot)
            self.assertNotIn('env', configured['status']['execution'])
            # forge is mutable alongside dispatch; the brief generation stays fixed.
            worker['spec']['forge'] = {'relay': {'notes': False}, 'draft': {'policy': None}}
            resources.write_text(json.dumps(worker))
            run('apply', '-f', str(resources), '--json', cfg=fake)
            run('send', name, 'Verify the documentation too.', '--json', cfg=fake)
            queued = run('get', 'task', name, cfg=fake)['status']['inbox'][0]
            run('reconcile', '--json', cfg=fake)
            delivered = run('get', 'task', name, cfg=fake)
            self.assertFalse(delivered['status'].get('inbox'))
            self.assertIn(queued['key'], [receipt['key'] for receipt in
                                       delivered['status']['deliveries']['receipts']])
            run('declare', name, '--json', '{"kind":"Note","text":"local validation"}', cfg=fake, json_output=False)
            declared = run('get', 'task', name, cfg=fake)
            self.assertEqual(declared['status']['declared'][0]['kind'], 'Note')
            self.assertNotIn('result', declared['status'])
            run('result', name, '--generation', str(configured['status']['brief']['generation']),
                '--outcome', 'shipped', '--summary', 'Verified locally', cfg=fake, json_output=False)
            run('reconcile', '--json', cfg=fake)
            concluded = run('get', 'task', name, cfg=fake)
            self.assertEqual(concluded['status']['phase'], 'Concluded')
            self.assertEqual(configured['status']['session'], concluded['status']['session'])
            # Declaration ensures a mirror; use only an offline fake forge.
            fake.write_text(fake.read_text() + '\n[forge.hosts]\n"forge.example" = { kind = "fake", dir = "fake-forge" }\n')
            url = 'https://forge.example/acme/widgets/pull/7'
            run('declare', name, '--change-request', url, cfg=fake, json_output=False)
            changes = run('list', 'changerequest', '--json', cfg=fake)
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]['spec']['url'], url)
            self.assertEqual(run('get', 'task', name, cfg=fake)['status']['declared'][-1]['kind'],
                             'ChangeRequest')



if __name__ == '__main__':
    unittest.main()
