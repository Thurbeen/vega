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
            for entry_point in [instructions, mission_control]:
                self.assertIn('existing owned task session', entry_point.lower())
                self.assertIn('direct prompts do not authorize substantive work',
                              ' '.join(entry_point.split()).lower())
                self.assertIn('task-status', entry_point.lower())
            self.assertIn('guarded task-status workflow', instructions.lower())
            self.assertIn('during a working turn', mission_control.lower())
            self.assertIn('do not use terminal access', mission_control.lower())
            for contract in [
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
                self.assertIn(contract.lower(), task_status.lower())
            normalized_status = ' '.join(task_status.split()).lower()
            for safety_rule in [
                'Do not default to `--force`',
                'not approve a trust or permission prompt',
                'do not direct-send and durable-send the same instruction',
                'capture again after `--no-enter`',
                'same composer',
            ]:
                self.assertIn(safety_rule.lower(), normalized_status)
            self.assertIn('new substantive request', task_status.lower())
            self.assertIn('new task', task_status.lower())
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


# A stand-in for thurbox-cli: it records each call, reports a ready local
# multiplexer and refuses every session create, so Fleet's real thurbox adapter
# shows the workspace it would ask for without touching a live runtime.
THURBOX_STUB = '''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calls.jsonl'), 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1:2] == ['doctor']:
    print(json.dumps({'checks': [{'key': 'multiplexer', 'level': 'ok'}]}))
elif sys.argv[1:3] == ['session', 'list']:
    print('[]')
else:
    sys.exit(1)
'''


@unittest.skipUnless(os.name == 'posix', 'the thurbox-cli stand-in is a POSIX script')
class Workspaces(unittest.TestCase):
    """Repository work reaches the runtime as a runtime-owned workspace."""

    def setUp(self):
        self.fleet = os.environ.get('FLEET_BIN')
        self.assertTrue(self.fleet, 'Set FLEET_BIN to the compatible Fleet binary; integration is required')
        self.tmp = Path(tempfile.mkdtemp(prefix='vega-test-', dir=ROOT))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.workspace = self.tmp / 'workspace'
        for asset in tomllib.loads((ROOT / 'starter.toml').read_text())['files']:
            if asset.startswith('workspace/'):
                target = self.tmp / asset
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / asset, target)

    def read(self, asset):
        return ' '.join((self.workspace / asset).read_text().split())

    def intake_tasks(self):
        text = (self.workspace / '.agents/skills/task-intake/SKILL.md').read_text()
        resources = [json.loads(block.split('```', 1)[0]) for block in text.split('```json\n')[1:]]
        return [r for r in resources if r['kind'] == 'Task']

    def spawn(self, task, mapped):
        """Apply TASK through Fleet's thurbox adapter; return its argv and status."""
        stub = self.tmp / 'thurbox-cli'
        stub.write_text(THURBOX_STUB)
        stub.chmod(0o755)
        source = self.tmp / 'source checkout'
        source.mkdir(exist_ok=True)
        config = self.tmp / 'thurbox.toml'
        config.write_text('version = 1\n[data]\ndir = "data"\n[runtime]\nkind = "thurbox"\n'
                          f'cli = {json.dumps(str(stub))}\nkeyPrefix = "vega"\n'
                          '[runtime.repositories]\n'
                          + ''.join(f'{json.dumps(url)} = {json.dumps(str(source))}\n' for url in mapped))
        task = json.loads(json.dumps(task))
        task['spec']['dispatch'] = True
        resource = self.tmp / 'task.json'
        resource.write_text(json.dumps(task))

        def run(*args):
            result = subprocess.run([self.fleet, '--config', str(config), *args],
                                    text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

        run('apply', '-f', str(resource), '--json')
        run('reconcile', '--max-passes', '3', '--json')
        status = json.loads(run('get', 'task', task['metadata']['name']))
        log = self.tmp / 'calls.jsonl'
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        creates = [c for c in calls if c[:2] == ['session', 'create']]
        return creates, status, source

    def test_the_repository_example_becomes_a_runtime_worktree(self):
        # VEGA used to hand every worker a directory it prepared itself, so
        # thurbox never made a worktree. The shipped repository example must
        # name its repositories and reach thurbox as one worktree create on a
        # branch the runtime names, from the base the example gives.
        tasks = self.intake_tasks()
        self.assertTrue(tasks, 'task-intake ships no Task example')
        for example in tasks:
            self.assertIn('repositories', example['spec']['workspace'],
                          f"Task example {example['metadata']['name']} still prepares a directory")
        task = tasks[0]
        workspace = task['spec']['workspace']
        primary = workspace['repositories'][0]
        self.assertTrue(primary['ref'].startswith('origin/'),
                        'thurbox does not fetch: the example base must be a remote-tracking ref')
        creates, status, source = self.spawn(task, [r['url'] for r in workspace['repositories']])
        self.assertEqual(len(creates), 1, status['status'].get('conditions'))
        argv = creates[0]
        uid = status['metadata']['uid']
        self.assertEqual(argv[argv.index('--repo-path') + 1], str(source))
        self.assertEqual(argv[argv.index('--worktree-branch') + 1],
                         f"vega/{task['metadata']['name']}.{uid}")
        self.assertEqual(argv[argv.index('--base-branch') + 1], primary['ref'])

    def test_an_unmapped_repository_is_mapped_before_it_spawns(self):
        # An unmapped URL never reaches thurbox. VEGA maps it itself, to an
        # existing source checkout, instead of falling back to a directory or
        # a checkout of its own. The waiting Task must not spend its spawn
        # attempts meanwhile, or it stalls before the mapping lands.
        task = self.intake_tasks()[0]
        creates, status, _ = self.spawn(task, [])
        self.assertEqual(creates, [])
        conditions = {c['type']: c for c in status['status']['conditions']}
        self.assertEqual(conditions['Spawned']['reason'], 'RepositoryUnmapped', conditions)
        self.assertEqual(conditions['NeedsAttention']['reason'], 'RepositoryUnmapped', conditions)
        self.assertEqual(status['status'].get('spawnAttempts', 0), 0)
        self.assertEqual(status['status']['phase'], 'Pending')
        mapped = json.loads(json.dumps(task))
        mapped['metadata']['name'] += '-mapped'
        urls = [r['url'] for r in task['spec']['workspace']['repositories']]
        creates, status, source = self.spawn(mapped, urls)
        self.assertEqual(len(creates), 1, status['status'].get('conditions'))
        self.assertEqual(creates[0][creates[0].index('--repo-path') + 1], str(source))
        intake = self.read('.agents/skills/task-intake/SKILL.md')
        for rule in ['An unmapped URL fails the spawn',
                     'add the mapping yourself',
                     'existing source checkout',
                     'ask the user and wait',
                     'without a restart',
                     'exact URL']:
            self.assertIn(rule, intake)
        self.assertNotIn('report it instead of adding a mapping', intake)

    def test_the_documented_mapping_check_refuses_a_bad_mapping(self):
        # `fleet list` never opens the runtime, so a relative source passed it
        # and only broke `fleet up` after the restart. The check task-intake
        # documents must refuse such a mapping before the live config changes,
        # without touching the live store or the runtime.
        intake = self.read('.agents/skills/task-intake/SKILL.md')
        command = intake.split('`fleet --config CANDIDATE', 1)[1].split('`', 1)[0].split()
        self.assertIn('--data-dir', command)
        stub = self.tmp / 'thurbox-cli'
        stub.write_text(THURBOX_STUB)
        stub.chmod(0o755)
        live = self.tmp / 'live store'
        for source, code in [('relative/source', 1), (str(self.tmp), 0)]:
            candidate = self.tmp / 'candidate.toml'
            candidate.write_text(f'version = 1\n[data]\ndir = {json.dumps(str(live))}\n'
                                 f'[runtime]\nkind = "thurbox"\ncli = {json.dumps(str(stub))}\n'
                                 'keyPrefix = "vega"\n[runtime.repositories]\n'
                                 f'"https://forge.example/acme/app" = {json.dumps(source)}\n')
            scratch = Path(tempfile.mkdtemp(dir=self.tmp))
            argv = [scratch.as_posix() if arg == 'EMPTY_DIR' else arg for arg in command]
            result = subprocess.run([self.fleet, '--config', str(candidate), *argv],
                                    text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertFalse(live.exists())
        self.assertFalse((self.tmp / 'calls.jsonl').exists())

    def test_guidance_leaves_checkouts_to_the_runtime(self):
        # VEGA's own entry points must not tell it to provision Git; the
        # prepared-directory form is an exception the user must ask for.
        intake = self.read('.agents/skills/task-intake/SKILL.md')
        surfaces = [self.read('AGENTS.md'), self.read('prompts/mission-control.md'), intake]
        for text in surfaces:
            for stale in ['A Task does not create a checkout',
                          'Prepare a separate existing absolute workspace',
                          'and isolated workspace',
                          'prepare briefs and isolated workspaces']:
                self.assertNotIn(stale, text)
        for rule in ['`runtime.repositories`',
                     'only when the user explicitly asks for that exception',
                     'a repository or a `dir` exception',
                     'Never clone, add a worktree or prepare a checkout',
                     "outside Fleet's data directory and outside this workspace",
                     'the worker makes any checkout',
                     'one entry per repository',
                     'removes its worktrees, its branch and any unpushed commits',
                     'Existing `dir` Tasks finish in place']:
            self.assertIn(rule, intake)
        status = self.read('.agents/skills/task-status/SKILL.md')
        self.assertIn('unpushed commits', status)



if __name__ == '__main__':
    unittest.main()
