"""Exercise distributable assets through the installed Fleet Task API."""
import json
import os
import re
import shlex
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
            for rule in ['open every change as a draft',
                         'fleet declare TASK --change-request URL',
                         '<!-- fleet:worker <task uid> -->',
                         'fleet get task TASK']:
                self.assertIn(rule, ' '.join(intake.split()))
            # The installed prompt surface must make Mission Control an
            # orchestration-only role for every substantive kind of request.
            for category in ['design', 'implementation', 'bug fix', 'test',
                             'research', 'review', 'writing', 'operational']:
                self.assertIn(category, instructions.lower())
            for content in [instructions, mission_control, intake, task_template]:
                self.assertIn('dispatch-only', content.lower())
            for boundary in ['acknowledge', 'clarify', 'status']:
                self.assertIn(boundary, instructions.lower())
            self.assertIn('without a repository', intake.lower())
            self.assertIn('isolated', intake.lower())
            self.assertIn('do not redo', task_status.lower())
            for content in [intake, task_status]:
                self.assertIn('required by slayer or the repository', content.lower())
                self.assertIn('draft-only', content.lower())
            # A clean install must let Mission Control coordinate an existing
            # Task session without weakening the dispatch-only boundary. These
            # are documentation contract checks; FakeRuntime does not simulate
            # a live terminal or prove that an agent will obey the guidance.
            normalized_instructions = ' '.join(instructions.split()).lower()
            for rule in ['existing owned task session',
                         'direct prompts do not authorize substantive work',
                         'guarded task-status workflow',
                         'do not use terminal access']:
                self.assertIn(rule, normalized_instructions)
            self.assertIn('task-status', mission_control.lower())
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



# Headings every worker brief carries, in order. A worker shares no context
# with Mission Control, so these are the only places it learns the request,
# its limits, the work around it and how to finish.
BRIEF_SECTIONS = ['Request', 'Goal', 'Constraints', 'Coordination', 'Done means']
EXAMPLE_CONFIG = '/absolute/path/to/fleet.toml'
# Always-loaded Mission Control context: workspace instructions, startup
# prompt and the initial Task brief. Skills load on demand and are excluded.
STARTUP_WORD_BUDGET = 1000


class Install:
    """A throwaway allowlisted installation driven by the real Fleet CLI."""

    def __init__(self, case, tmp):
        self.case = case
        self.fleet = os.environ.get('FLEET_BIN')
        case.assertTrue(self.fleet, 'Set FLEET_BIN to the compatible Fleet binary; integration is required')
        self.root = Path(tmp)
        for asset in tomllib.loads((ROOT / 'starter.toml').read_text())['files']:
            target = self.root / asset
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / asset, target)
        self.workspace = self.root / 'workspace'
        runtime = tomllib.loads((self.root / 'config/fleet.toml').read_text())['runtime']
        runtime['kind'] = 'fake'
        self.config = self.root / 'config/fake.toml'
        self.config.write_text(
            'version = 1\n[data]\ndir = "data"\n[runtime]\n'
            + '\n'.join(f'{key} = {json.dumps(value)}' for key, value in runtime.items())
            + '\ndir = "fake-host"\n'
            + '[forge.hosts]\n"forge.example" = { kind = "fake", dir = "fake-forge" }\n')

    def read(self, asset):
        return (self.root / asset).read_text()

    def run(self, *args, json_output=True):
        result = subprocess.run([self.fleet, '--config', str(self.config), *args],
                                text=True, capture_output=True, timeout=20)
        self.case.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout) if json_output else result.stdout

    def apply(self, resource):
        path = self.root / f'{resource["metadata"]["name"]}.json'
        path.write_text(json.dumps(resource))
        self.run('apply', '-f', str(path), '--json')

    def session(self, name):
        """The FakeRuntime host's record of Task NAME's session."""
        key = self.run('get', 'task', name)['status']['session']['key']
        state = json.loads((self.config.parent / 'fake-host/state.json').read_text())
        return state['sessions'][key]

    def delivered_text(self, name):
        """What the FakeRuntime session for Task NAME actually received."""
        return self.session(name)['texts']


def brief_sections(brief):
    """Map each `## Heading` of a brief to its body, in order."""
    sections = {}
    current = None
    for line in brief.splitlines():
        if line.startswith('## '):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: '\n'.join(body).strip() for name, body in sections.items()}


class Briefs(unittest.TestCase):
    """Acceptance scenarios for what Mission Control hands to a worker."""

    def test_shipped_worker_brief_alone_lets_a_worker_finish(self):
        # A worker reads nothing but its delivered brief. The shipped example
        # must therefore carry the request, scope, coordination and an exact,
        # runnable way to record its result against Mission Control's store.
        with tempfile.TemporaryDirectory(prefix='vega-test-', dir=ROOT) as tmp:
            install = Install(self, tmp)
            intake = install.read('workspace/.agents/skills/task-intake/SKILL.md')
            self.assertIn('```markdown\n', intake, 'task-intake ships no example worker brief')
            brief = intake.split('```markdown\n')[1].split('```\n', 1)[0].strip()
            task = json.loads(intake.split('```json\n')[1].split('```', 1)[0])
            name = task['metadata']['name']
            # Repository work names its repositories and the runtime makes the
            # checkout, so the example applies without a prepared directory.
            workspace = task['spec']['workspace']
            self.assertEqual(list(workspace), ['repositories'],
                             'example repository Task still needs a prepared directory')
            self.assertFalse('does not create a checkout' in ' '.join(intake.split()),
                             'task-intake still says a Task never gets a checkout')
            # Mission Control serializes the brief and renders its config.
            task['spec']['brief'] = brief.replace(EXAMPLE_CONFIG, str(install.config))
            self.assertFalse(task['spec']['dispatch'])
            install.apply(task)
            task['spec']['dispatch'] = True
            install.apply(task)
            install.run('reconcile', '--json')
            # The runtime received the repositories to materialize, unchanged.
            self.assertEqual(install.session(name)['workspace'], workspace)
            [delivered] = install.delivered_text(name)
            self.assertEqual(delivered, task['spec']['brief'])
            sections = brief_sections(delivered)
            self.assertEqual(list(sections), BRIEF_SECTIONS,
                             'delivered brief lacks the ordered worker sections')
            for section, body in sections.items():
                self.assertTrue(body, f'empty brief section {section}')
            self.assertNotIn('{{', delivered)
            # Run the brief's own Fleet commands exactly as a worker would.
            commands = [shlex.split(c) for c in re.findall(r'`(fleet --config [^`]+)`', delivered)]
            self.assertTrue(commands, 'delivered brief names no runnable Fleet command')
            for command in commands:
                self.assertEqual(command[2], str(install.config),
                                 'brief command does not address Mission Control config')
            verbs = {command[3]: command for command in commands}
            self.assertLessEqual({'get', 'declare', 'result'}, set(verbs))
            uid = install.run(*verbs['get'][3:])['metadata']['uid']
            self.assertIn('<!-- fleet:worker <task uid> -->', sections['Done means'])
            self.assertIn('draft', sections['Done means'])
            url = 'https://forge.example/acme/widgets/pull/7'
            install.run(*[url if arg == 'URL' else arg for arg in verbs['declare'][3:]],
                        json_output=False)
            generation = install.run('get', 'task', name)['status']['brief']['generation']
            fill = {'GENERATION': str(generation), 'OUTCOME': 'shipped',
                    'SUMMARY': f'Fixed; checks pass; {uid}', 'URL': url}
            install.run(*[fill.get(arg, arg) for arg in verbs['result'][3:]], json_output=False)
            install.run('reconcile', '--json')
            concluded = install.run('get', 'task', name)
            self.assertEqual(concluded['status']['phase'], 'Concluded')
            self.assertEqual(concluded['status']['declared'][-1]['kind'], 'ChangeRequest')

    def test_startup_context_is_small_and_each_standing_rule_has_one_home(self):
        # Every word of the always-loaded surface is read on each start and
        # competes with the user's request. Repeated rules drift apart.
        with tempfile.TemporaryDirectory(prefix='vega-test-', dir=ROOT) as tmp:
            install = Install(self, tmp)
            startup = [install.read('workspace/AGENTS.md'),
                       install.read('workspace/prompts/mission-control.md'),
                       json.loads(install.read('tasks/vega.json'))[0]['spec']['brief']]
            words = sum(len(text.split()) for text in startup)
            self.assertLessEqual(words, STARTUP_WORD_BUDGET,
                                 f'always-loaded startup context is {words} words')
            shipped = {asset: install.read(asset) for asset in
                       tomllib.loads((ROOT / 'starter.toml').read_text())['files']
                       if asset.startswith(('workspace/', 'tasks/'))}
            for rule in ['<!-- fleet:worker <task uid> -->',
                         'fleet declare TASK --change-request URL',
                         'Short, read-only, urgent or repository-free work']:
                homes = [asset for asset, text in shipped.items()
                         if rule in ' '.join(text.split())]
                self.assertEqual(len(homes), 1, f'{rule!r} is stated in {homes}')


# VEGA's own name and the name it uses for its human. Generic references to
# "the user" would leave a session unsure who it is talking to.
ASSISTANT_NAME = 'VEGA'
HUMAN_NAME = 'Slayer'
GENERIC_HUMAN = re.compile(r"\b(?:the|a) user\b|\buser's\b", re.IGNORECASE)


class Identity(unittest.TestCase):
    """Acceptance scenario for how a started VEGA session names itself and its human."""

    def test_started_session_knows_it_is_vega_working_for_slayer(self):
        with tempfile.TemporaryDirectory(prefix='vega-test-', dir=ROOT) as tmp:
            install = Install(self, tmp)
            [task] = json.loads(install.read('tasks/vega.json'))
            task['spec']['workspace']['dir'] = str(install.workspace)
            install.apply(task)
            install.run('reconcile', '--json')
            [delivered] = install.delivered_text('vega')
            # The text the session actually received names both parties.
            self.assertIn(f'You are {ASSISTANT_NAME}', delivered)
            self.assertIn(HUMAN_NAME, delivered)
            # The always-loaded rules and every shipped skill VEGA follows
            # address the human by name, never as an anonymous user.
            shipped = {asset: install.read(asset) for asset in
                       tomllib.loads((ROOT / 'starter.toml').read_text())['files']
                       if asset.startswith(('workspace/', 'tasks/'))}
            self.assertIn(HUMAN_NAME, shipped['workspace/AGENTS.md'])
            generic = {asset: GENERIC_HUMAN.findall(' '.join(text.split()))
                       for asset, text in shipped.items()}
            self.assertEqual({a: m for a, m in generic.items() if m}, {},
                             f'shipped guidance calls {HUMAN_NAME} "the user"')


ISSUE_SKILL = 'workspace/.agents/skills/issue-intake/SKILL.md'
ISSUE_URL = re.compile(r'https://\S+?/issues/\d+')


def frontmatter(skill):
    """The `key: value` header of a SKILL.md package."""
    header = skill.split('---\n')[1]
    return dict(line.split(': ', 1) for line in header.strip().splitlines())


class Issues(unittest.TestCase):
    """Acceptance scenarios for routing a forge issue to one worker Task."""

    def test_issue_skill_installs_and_vega_can_find_every_skill(self):
        with tempfile.TemporaryDirectory(prefix='vega-test-', dir=ROOT) as tmp:
            install = Install(self, tmp)
            self.assertTrue((install.root / ISSUE_SKILL).is_file(),
                            'a clean installation has no issue skill')
            instructions = install.read('workspace/AGENTS.md')
            readme = (ROOT / 'README.md').read_text()
            skills = sorted((install.workspace / '.agents/skills').glob('*/SKILL.md'))
            self.assertGreaterEqual(len(skills), 3)
            for path in skills:
                meta = frontmatter(path.read_text())
                self.assertEqual(meta['name'], path.parent.name)
                self.assertTrue(meta['description'])
                self.assertEqual(meta['license'], 'MIT')
                # Always-loaded instructions name each skill VEGA must load,
                # and the source README documents each shipped file.
                relative = path.relative_to(install.workspace).as_posix()
                self.assertIn(relative, instructions, f'AGENTS.md never names {relative}')
                self.assertTrue(f'workspace/{relative}' in readme, f'README never documents {relative}')
            self.assertIn('issue', frontmatter(install.read(ISSUE_SKILL))['description'].lower())

    def test_an_issue_task_names_its_repository_and_is_found_by_its_issue(self):
        # Before briefing an issue, VEGA looks for a Task that already owns it.
        # That lookup only works if an issue brief carries the issue URL, and
        # the Task must check out the repository that issue belongs to.
        with tempfile.TemporaryDirectory(prefix='vega-test-', dir=ROOT) as tmp:
            install = Install(self, tmp)
            self.assertTrue((install.root / ISSUE_SKILL).is_file(),
                            'a clean installation has no issue skill')
            skill = ' '.join(install.read(ISSUE_SKILL).split())
            # The skill routes through the shared intake and status skills
            # instead of keeping its own copy of their rules or examples.
            for shared in ['task-intake', 'task-status']:
                self.assertIn(shared, skill)
            self.assertNotIn('```json', skill)
            self.assertIn('fleet list task --json', skill)
            intake = install.read('workspace/.agents/skills/task-intake/SKILL.md')
            brief = intake.split('```markdown\n')[1].split('```\n', 1)[0]
            task = json.loads(intake.split('```json\n')[1].split('```', 1)[0])
            task['spec']['brief'] = brief
            install.apply(task)
            install.run('reconcile', '--json')
            [issue] = set(ISSUE_URL.findall(brief))
            [repository] = task['spec']['workspace']['repositories']
            self.assertEqual(issue.rsplit('/issues/', 1)[0], repository['url'])
            owners = [t['metadata']['name'] for t in install.run('list', 'task', '--json')
                      if issue in t['spec']['brief']]
            self.assertEqual(owners, [task['metadata']['name']])



if __name__ == '__main__':
    unittest.main()
