"""Exercise distributable assets through the installed Fleet Task API."""
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shlex
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
        # No VEGA Task exists here to be the parent; MissionControl covers it.
        labels = task['metadata'].get('labels', {})
        for key in [k for k in labels if k.startswith('gateway.fleet.dev/parent')]:
            del labels[key]
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
        for rule in ['An unmapped URL leaves the Task Pending with `NeedsAttention`/`RepositoryUnmapped`',
                     'reports `version` 2.7.3 or later',
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


def sh_blocks(text):
    """The shell commands a skill or prompt ships, in order."""
    return [block.split('```', 1)[0].strip() for block in text.split('```sh\n')[1:]]


class MissionControl(unittest.TestCase):
    """VEGA answers at once, keeps its state in Fleet and can be cleared.

    Mission Control used to wait in the foreground for its workers, grow its
    context until the harness compacted it, and keep serial lanes, owners and
    pending questions in its own memory files. These checks run the commands
    the installed guidance ships against the real Fleet binary with
    FakeRuntime: a worker reports back through VEGA's inbox, the status digest
    rebuilds the whole working state from Fleet, and the clear protocol is two
    ordinary inbox deliveries. They cannot prove a model obeys the prose.
    """

    def setUp(self):
        fleet = os.environ.get('FLEET_BIN')
        self.assertTrue(fleet, 'Set FLEET_BIN to the compatible Fleet binary; integration is required')
        self.assertTrue(shutil.which('jq'), 'the status digest needs jq')
        self.tmp = Path(tempfile.mkdtemp(prefix='vega-test-', dir=ROOT))
        self.addCleanup(shutil.rmtree, self.tmp)
        for asset in tomllib.loads((ROOT / 'starter.toml').read_text())['files']:
            if asset.startswith('workspace/'):
                target = self.tmp / asset
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / asset, target)
        self.workspace = self.tmp / 'workspace'
        # The guidance assumes `fleet` on PATH and FLEET_CONFIG exported.
        bin_dir = self.tmp / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'fleet').symlink_to(Path(fleet).resolve())
        self.config = self.tmp / 'fleet.toml'
        self.config.write_text('version = 1\n[data]\ndir = "data"\n[runtime]\nkind = "fake"\ndir = "fake-host"\n')
        self.env = dict(os.environ, PATH=f'{bin_dir}{os.pathsep}{os.environ["PATH"]}',
                        FLEET_CONFIG=str(self.config))
        vega = json.loads((ROOT / 'tasks/vega.json').read_text())
        vega[0]['spec']['workspace']['dir'] = str(self.workspace)
        self.apply(vega)
        self.fleet('reconcile', '--json')
        self.assertEqual(self.get('vega')['status']['phase'], 'Briefed')

    def sh(self, command, **subst):
        for key, value in subst.items():
            command = command.replace(key, value)
        result = subprocess.run(['bash', '-euo', 'pipefail', '-c', command], text=True,
                                capture_output=True, timeout=20, env=self.env, cwd=self.tmp)
        self.assertEqual(result.returncode, 0, command + '\n' + result.stdout + result.stderr)
        return result.stdout

    def fleet(self, *args):
        return self.sh(' '.join(['fleet', *map(shlex.quote, args)]))

    def get(self, name):
        return json.loads(self.fleet('get', 'task', name))

    def apply(self, resource):
        path = self.tmp / 'resource.json'
        path.write_text(json.dumps(resource))
        self.fleet('apply', '-f', str(path), '--json')

    def text(self, asset):
        return (self.workspace / asset).read_text()

    def worker(self, name, dispatch, **labels):
        """The task-intake example, as VEGA fills it in for one request."""
        intake = self.text('.agents/skills/task-intake/SKILL.md')
        task = json.loads(intake.split('```json\n', 1)[1].split('```', 1)[0])
        task['metadata']['name'] = name
        uid = self.sh(sh_blocks(intake)[0]).strip()
        task['metadata']['labels'] = {key: uid if value == 'VEGA_UID' else value
                                      for key, value in task['metadata']['labels'].items()}
        task['metadata']['labels'].update(labels)
        task['spec']['dispatch'] = dispatch
        return task

    def test_always_loaded_guidance_stays_small(self):
        # Every turn pays for AGENTS.md and the startup prompt; they used to
        # repeat each other at about 1,400 words.
        words = sum(len(self.text(a).split()) for a in ['AGENTS.md', 'prompts/mission-control.md'])
        self.assertLessEqual(words, 800)

    def test_guidance_never_waits_in_the_foreground(self):
        surfaces = {a: self.text(a) for a in [
            'AGENTS.md', 'prompts/mission-control.md',
            '.agents/skills/task-intake/SKILL.md', '.agents/skills/task-status/SKILL.md',
            '.agents/skills/status-digest/SKILL.md']}
        surfaces['tasks/vega.json'] = (ROOT / 'tasks/vega.json').read_text()
        for asset, text in surfaces.items():
            # Only commands count: the prose may name what it forbids.
            fenced = text.split('```')[1::2]
            inline = ''.join(text.split('```')[0::2]).split('`')[1::2]
            for command in fenced + inline:
                for blocking in ['--wait-turn', 'sleep ', 'until ', 'while ', 'watch ',
                                 'session wait']:
                    self.assertNotIn(blocking, command, asset)
        for asset in ['AGENTS.md', 'prompts/mission-control.md', 'tasks/vega.json']:
            flat = ' '.join(surfaces[asset].split()).lower()
            self.assertIn('never wait in the foreground', flat, asset)
            self.assertIn('background', flat, asset)
        for asset in ['AGENTS.md', 'prompts/mission-control.md']:
            flat = ' '.join(surfaces[asset].split()).lower()
            self.assertIn('fleet is the source of truth', flat, asset)
            self.assertIn('user preferences only', flat, asset)

    def test_a_worker_reports_back_through_vegas_inbox(self):
        # VEGA does not wait for a worker: the parent labels task-intake puts
        # on every Task relay its Questions, change requests and result into
        # VEGA's own session as Fleet messages.
        self.apply(self.worker('fix-login', True))
        self.fleet('reconcile', '--json')
        self.assertEqual(self.get('fix-login')['status']['phase'], 'Briefed')
        self.fleet('declare', 'fix-login', '--json',
                   '{"kind":"Question","id":"q1","text":"Keep the old endpoint?"}')
        self.fleet('reconcile', '--json')
        self.fleet('result', 'fix-login', '--generation', '1', '--outcome', 'shipped',
                   '--summary', 'Opened the draft')
        self.fleet('reconcile', '--json')
        received = [r['key'] for r in self.get('vega')['status']['deliveries']['receipts']
                    if r['from'] == 'gateway/child/fix-login']
        self.assertEqual(len(received), 2, received)
        self.assertTrue(received[-1].endswith('/result/1'), received)

    def test_the_status_digest_rebuilds_state_from_fleet(self):
        # Serial lanes, limits, open questions and change ownership live on
        # the Tasks, so a cleared or restarted VEGA reads them back from Fleet.
        digest_skill = self.text('.agents/skills/status-digest/SKILL.md')
        digest, set_label, release = sh_blocks(digest_skill)
        self.apply(self.worker('fix-login', True, **{'vega.fleet.dev/limits': 'draft-only no-merge'}))
        self.apply(self.worker('fix-logout', False, **{'vega.fleet.dev/after': 'fix-login'}))
        self.fleet('reconcile', '--json')
        self.fleet('declare', 'fix-login', '--json',
                   '{"kind":"Question","id":"q1","text":"Keep the old endpoint?"}')
        board = self.sh(digest).splitlines()
        self.assertEqual(len(board), 2, board)
        lines = {line.split()[0]: line for line in board}
        self.assertNotIn('vega', lines)
        self.assertIn('limits:draft-only no-merge', lines['fix-login'])
        self.assertIn('ask:q1', lines['fix-login'])
        self.assertIn('held', lines['fix-logout'])
        self.assertIn('after:fix-login', lines['fix-logout'])
        self.assertNotIn('{', '\n'.join(board), 'the digest must not dump JSON')
        # A failed or stuck predecessor must not start the rest of its lane.
        for text in [digest_skill, self.text('prompts/mission-control.md')]:
            self.assertIn('verified `shipped`', ' '.join(text.split()))
        self.fleet('send', 'fix-login', '--answers', 'q1', 'Yes')
        self.sh(set_label, NAME='fix-logout')
        self.assertIn('needs:', self.sh(digest))
        self.assertNotIn('ask:q1', self.sh(digest))
        generation = self.get('fix-logout')['metadata']['generation']
        self.sh(release, NAME='fix-logout')
        released = self.get('fix-logout')
        self.assertTrue(released['spec']['dispatch'])
        self.assertFalse({'vega.fleet.dev/after', 'vega.fleet.dev/needs'}
                         & set(released['metadata'].get('labels', {})))
        self.assertEqual(released['metadata']['labels']['gateway.fleet.dev/parent'], 'vega')
        self.assertEqual(released['metadata']['generation'], generation + 1)

    def test_questions_reach_the_user_as_choices_and_answers_go_back(self):
        # A relayed worker Question used to reach the user as prose to be
        # answered by typing "1A 2B". VEGA now asks through the harness's
        # structured question tool when it has one and sends the choice back
        # with the answer command it ships.
        prompt = self.text('prompts/mission-control.md')
        section = prompt.split('## Ask the user\n', 1)[1].split('\n## ', 1)[0]
        flat = ' '.join(section.split())
        for required in ['AskUserQuestion', 'structured question tool', 'recommended option first',
                         'prose', 'open-ended', 'preferences', '`needs:`']:
            self.assertIn(required, flat)
        answer = [c for c in flat.split('`')[1::2] if '--answers' in c]
        self.assertEqual(answer, ['fleet send NAME --answers ID TEXT'])
        self.apply(self.worker('fix-login', True))
        self.fleet('reconcile', '--json')
        self.fleet('declare', 'fix-login', '--json',
                   '{"kind":"Question","id":"q1","text":"Keep the old endpoint?"}')
        digest = sh_blocks(self.text('.agents/skills/status-digest/SKILL.md'))[0]
        self.assertIn('ask:q1', self.sh(digest))
        self.sh(answer[0].replace('TEXT', "'Keep it (Recommended)'"), NAME='fix-login', ID='q1')
        self.assertNotIn('ask:q1', self.sh(digest))
        inbox = [entry['text'] for entry in self.get('fix-login')['status']['inbox']]
        self.assertTrue(any('Keep it (Recommended)' in text for text in inbox), inbox)

    def test_vega_clears_its_context_through_its_own_inbox(self):
        # Fleet types inbox messages into an idle session in order, so the
        # harness's clear command and the re-hydration prompt arrive as two
        # ordinary deliveries once VEGA's turn ends.
        prompt = self.text('prompts/mission-control.md')
        clear = [b for b in sh_blocks(prompt) if '/clear' in b]
        self.assertEqual(len(clear), 1, 'mission-control must ship one clear command block')
        self.sh(clear[0])
        inbox = [entry['text'] for entry in self.get('vega')['status']['inbox']]
        self.assertEqual(inbox[0], '/clear')
        self.assertIn('prompts/mission-control.md', inbox[1])
        self.fleet('reconcile', '--json')
        self.fleet('reconcile', '--json')
        self.assertFalse(self.get('vega')['status'].get('inbox'))



if __name__ == '__main__':
    unittest.main()
