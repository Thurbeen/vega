"""VEGA's guidance, run against the real Fleet v3 binary with the fake runtime.

./install.sh puts VEGA into a sandboxed store, then each check runs the
commands the installed guidance ships: a worker reports back through VEGA's
inbox, the status digest rebuilds the working state from Fleet, and
a dispatch writes only the task-specific brief. They cannot prove a model obeys
the prose.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / 'workspace'
GUIDANCE = ['AGENTS.md', 'prompts/mission-control.md', '.agents/skills/task-intake/SKILL.md',
            '.agents/skills/task-status/SKILL.md', '.agents/skills/status-digest/SKILL.md',
            'briefs/worker.md']


def text(asset):
    return (WORKSPACE / asset).read_text()


def sh_blocks(body):
    """The shell commands a skill or prompt ships, in order."""
    return [block.split('```', 1)[0].strip() for block in body.split('```sh\n')[1:]]


class MissionControl(unittest.TestCase):
    def setUp(self):
        fleet = os.environ.get('FLEET_BIN')
        self.assertTrue(fleet, 'Set FLEET_BIN to a Fleet v3 binary; integration is required')
        self.assertTrue(shutil.which('jq'), 'the status digest needs jq')
        self.tmp = Path(tempfile.mkdtemp(prefix='vega-test-', dir=ROOT))
        self.addCleanup(shutil.rmtree, self.tmp)
        bin_dir = self.tmp / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'fleet').symlink_to(Path(fleet).resolve())
        (bin_dir / 'codex').write_text('#!/bin/sh\nexit 0\n')
        (bin_dir / 'codex').chmod(0o755)
        self.config = self.tmp / 'fleet.toml'
        self.config.write_text('version = 1\n[data]\ndir = "data"\n[runtime]\nkind = "fake"\ndir = "fake-host"\n')
        # The guidance assumes `fleet` on PATH and FLEET_CONFIG set, as the
        # installer sets it on the Task.
        self.env = {'HOME': str(self.tmp), 'PATH': f'{bin_dir}{os.pathsep}{os.environ["PATH"]}',
                    'FLEET_CONFIG': str(self.config)}
        self.sh(f'{shlex.quote(str(ROOT / "install.sh"))} --harness codex')
        self.fleet('reconcile')
        vega = self.get('vega')
        self.assertEqual(vega['status']['phase'], 'Briefed')
        self.assertEqual(vega['spec']['env']['FLEET_CONFIG'], str(self.config))

    def sh(self, command, cwd=None, **subst):
        for key, value in subst.items():
            command = command.replace(key, value)
        result = subprocess.run(['bash', '-euo', 'pipefail', '-c', command], text=True,
                                capture_output=True, timeout=60, env=self.env, cwd=cwd or self.tmp)
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

    def manifest(self, name, dispatch, brief='Fix the login redirect.', limits='draft-only no-merge',
                 urls=('git+https://forge.example/acme/app.git',)):
        intake = text('.agents/skills/task-intake/SKILL.md')
        build, = [b for b in sh_blocks(intake) if b.startswith('jq -n')]
        workspace = self.tmp / 'vega-workspace'
        if not workspace.exists():
            shutil.copytree(WORKSPACE, workspace, ignore=shutil.ignore_patterns('dispatch', 'private'))
            (workspace / 'dispatch').mkdir()
        (workspace / 'dispatch' / f'{name}.txt').write_text(brief + '\n')
        self.sh(build, cwd=workspace, NAME=name, REQUEST='fix the login', LIMITS=limits,
                DISPATCH=json.dumps(dispatch), URL=' '.join(map(shlex.quote, urls)))
        return json.loads((workspace / 'dispatch' / f'{name}.json').read_text())

    def worker(self, name, dispatch, **labels):
        task = self.manifest(name, dispatch)
        task['metadata']['labels'].update(labels)
        return task

    def test_always_loaded_guidance_stays_small(self):
        words = sum(len(text(a).split()) for a in ['AGENTS.md', 'prompts/mission-control.md'])
        self.assertLessEqual(words, 800)

    def test_guidance_never_waits_in_the_foreground(self):
        surfaces = {a: text(a) for a in GUIDANCE}
        surfaces['tasks/vega.json'] = (ROOT / 'tasks/vega.json').read_text()
        for asset, body in surfaces.items():
            # Only commands count: the prose may name what it forbids.
            fenced = body.split('```')[1::2]
            inline = ''.join(body.split('```')[0::2]).split('`')[1::2]
            for command in fenced + inline:
                for blocking in ['sleep ', 'until ', 'while ', 'watch ']:
                    self.assertNotIn(blocking, command, asset)
        for asset in ['AGENTS.md', 'prompts/mission-control.md', 'tasks/vega.json']:
            flat = ' '.join(surfaces[asset].split()).lower()
            self.assertIn('never wait in the foreground', flat, asset)
            self.assertIn('background', flat, asset)
        for asset in ['AGENTS.md', 'prompts/mission-control.md']:
            flat = ' '.join(surfaces[asset].split()).lower()
            self.assertIn('fleet is the source of truth', flat, asset)
            self.assertIn('user preferences only', flat, asset)

    def test_guidance_names_only_what_fleet_v3_has(self):
        # Fleet v2's runtime mapping, Thurbox session commands and repository
        # objects are gone; places replace hosts.
        for asset in GUIDANCE + ['../README.md', '../AGENTS.md']:
            body = text(asset)
            for gone in ['runtime.repositories', 'thurbox-cli', 'keyPrefix', 'RepositoryUnmapped',
                         '"repositories"', 'session send', 'session capture', 'v2.', '"host"',
                         'runtime.modelEnv', '"model"']:
                self.assertNotIn(gone, body, asset)
            prose = re.sub(r'`[^`]*`', '', re.sub(r'```.*?```', '', body, flags=re.S))
            self.assertIsNone(re.search(r'\bhosts?\b', prose.lower()), asset)

    def test_the_worker_workspace_is_made_by_the_runtime(self):
        self.apply(self.worker('fix-login', True))
        self.fleet('reconcile')
        status = self.get('fix-login')['status']
        self.assertEqual(status['phase'], 'Briefed')
        self.assertEqual(len(status['workspace']['dirs']), 1)
        self.assertTrue(status['workspace']['key'].startswith('fix-login.'))

    def test_a_worker_reports_back_through_vegas_inbox(self):
        # VEGA does not wait for a worker: the parent labels task-intake puts
        # on every Task relay its Questions, change requests and result into
        # VEGA's own session as Fleet messages.
        self.apply(self.worker('fix-login', True))
        self.fleet('reconcile')
        self.assertEqual(self.get('fix-login')['status']['phase'], 'Briefed')
        self.fleet('declare', 'fix-login', '--json',
                   '{"kind":"Question","id":"q1","text":"Keep the old endpoint?"}')
        self.fleet('reconcile')
        self.fleet('result', 'fix-login', '--generation', '1', '--outcome', 'shipped',
                   '--summary', 'Opened the draft')
        self.fleet('reconcile')
        received = [r['key'] for r in self.get('vega')['status']['deliveries']['receipts']
                    if r['from'] == 'gateway/child/fix-login']
        self.assertEqual(len(received), 2, received)
        self.assertTrue(received[-1].endswith('/result/1'), received)

    def test_the_status_digest_rebuilds_state_from_fleet(self):
        digest_skill = text('.agents/skills/status-digest/SKILL.md')
        digest, set_label, release = sh_blocks(digest_skill)
        self.apply(self.worker('fix-login', True, **{'vega.fleet.dev/limits': 'draft-only no-merge'}))
        self.apply(self.worker('fix-logout', False, **{'vega.fleet.dev/after': 'fix-login'}))
        self.fleet('reconcile')
        self.fleet('declare', 'fix-login', '--json',
                   '{"kind":"Question","id":"q1","text":"Keep the old endpoint?"}')
        board = self.sh(digest).splitlines()
        self.assertEqual(len(board), 2, board)
        lines = {line.split()[0]: line for line in board}
        self.assertNotIn('vega', lines)
        self.assertIn('ask:q1', lines['fix-login'])
        for line in board:
            self.assertLessEqual(len(line), 60, 'one short line per Task')
            for long_field in ['limits:', 'request:', 'ws:', 'cr:', 'forge.example']:
                self.assertNotIn(long_field, line)
        self.assertIn('held', lines['fix-logout'])
        self.assertIn('after:fix-login', lines['fix-logout'])
        self.assertNotIn('{', '\n'.join(board), 'the digest must not dump JSON')
        for body in [digest_skill, text('prompts/mission-control.md')]:
            self.assertIn('verified `shipped`', ' '.join(body.split()))
        self.fleet('send', 'fix-login', '--answers', 'q1', 'Yes')
        self.sh(set_label, NAME='fix-logout')
        self.assertIn('needs:', self.sh(digest))
        self.assertNotIn('ask:q1', self.sh(digest))
        self.fleet('label', 'task', 'fix-logout', 'vega.fleet.dev/needs=')
        self.assertNotIn('needs:', self.sh(digest))
        generation = self.get('fix-logout')['metadata']['generation']
        self.sh(release, NAME='fix-logout')
        released = self.get('fix-logout')
        self.assertTrue(released['spec']['dispatch'])
        self.assertFalse({'vega.fleet.dev/after', 'vega.fleet.dev/needs'}
                         & set(released['metadata'].get('labels', {})))
        self.assertEqual(released['metadata']['labels']['gateway.fleet.dev/parent'], 'vega')
        self.assertEqual(released['metadata']['generation'], generation + 1)

    def test_questions_reach_the_user_as_choices_and_answers_go_back(self):
        prompt = text('prompts/mission-control.md')
        section = prompt.split('## Ask the user\n', 1)[1].split('\n## ', 1)[0]
        flat = ' '.join(section.split())
        for required in ['AskUserQuestion', 'structured question tool', 'recommended option first',
                         'prose', 'open-ended', 'preferences',
                         '`needs:` decision always goes to the user', 'ask last',
                         'label a `needs:` answer as status-digest shows']:
            self.assertIn(required, flat)
        answer = [c for c in flat.split('`')[1::2] if '--answers' in c]
        self.assertEqual(answer, ['fleet send NAME --answers ID TEXT'])
        self.apply(self.worker('fix-login', True))
        self.fleet('reconcile')
        self.fleet('declare', 'fix-login', '--json',
                   '{"kind":"Question","id":"q1","text":"Keep the old endpoint?"}')
        digest = sh_blocks(text('.agents/skills/status-digest/SKILL.md'))[0]
        self.assertIn('ask:q1', self.sh(digest))
        self.sh(answer[0].replace('TEXT', "'Keep it (Recommended)'"), NAME='fix-login', ID='q1')
        self.assertNotIn('ask:q1', self.sh(digest))
        inbox = [entry['text'] for entry in self.get('fix-login')['status']['inbox']]
        self.assertTrue(any('Keep it (Recommended)' in t for t in inbox), inbox)

    def test_vega_rehydrates_only_when_its_context_was_cleared(self):
        for asset in GUIDANCE:
            body = text(asset)
            self.assertNotIn('fleet send vega', body, asset)
            self.assertNotIn('re-hydrate:', body, asset)
        prompt = ' '.join(text('prompts/mission-control.md').split()).lower()
        self.assertIn('only at session start or after a clear', prompt)

    def test_a_finished_task_leaves_the_digest(self):
        digest = sh_blocks(text('.agents/skills/status-digest/SKILL.md'))[0]
        self.apply(self.worker('fix-login', True))
        self.apply(self.worker('fix-logout', True))
        self.fleet('reconcile')
        for name in ['fix-login', 'fix-logout']:
            self.fleet('result', name, '--generation', '1', '--outcome', 'shipped', '--summary', 'Done')
        self.fleet('declare', 'fix-logout', '--json', '{"kind":"Question","id":"q1","text":"Also v1?"}')
        self.fleet('reconcile')
        board = self.sh(digest).splitlines()
        self.assertEqual([line.split()[0] for line in board], ['fix-logout'], board)
        self.assertIn('ask:q1', board[0])

    def test_a_task_that_did_not_ship_stays_on_the_digest(self):
        digest = sh_blocks(text('.agents/skills/status-digest/SKILL.md'))[0]
        self.apply(self.worker('fix-login', True))
        self.apply(self.worker('fix-logout', False, **{'vega.fleet.dev/after': 'fix-login'}))
        self.fleet('reconcile')
        self.fleet('result', 'fix-login', '--generation', '1', '--outcome', 'stuck', '--summary', 'Blocked')
        self.fleet('reconcile')
        lines = {line.split()[0]: line for line in self.sh(digest).splitlines()}
        self.assertIn('result:stuck', lines['fix-login'])
        self.assertIn('after:fix-login', lines['fix-logout'])
        self.fleet('label', 'task', 'fix-logout', 'vega.fleet.dev/after=')
        self.assertNotIn('fix-login ', self.sh(digest))

    def test_a_task_with_nothing_to_do_leaves_the_digest(self):
        digest = sh_blocks(text('.agents/skills/status-digest/SKILL.md'))[0]
        self.apply(self.worker('review-login', True))
        self.fleet('reconcile')
        self.fleet('result', 'review-login', '--generation', '1', '--outcome', 'not-applicable',
                   '--summary', 'Nothing to do')
        self.fleet('reconcile')
        self.assertEqual(self.sh(digest).strip(), '')
        self.apply(self.worker('fix-review', False, **{'vega.fleet.dev/after': 'review-login'}))
        lines = {line.split()[0]: line for line in self.sh(digest).splitlines()}
        self.assertIn('result:not-applicable', lines['review-login'])

    def test_the_overlap_search_reads_workspaces_labels_and_changes_only(self):
        intake = text('.agents/skills/task-intake/SKILL.md')
        search, = [b for b in sh_blocks(intake) if b.startswith('fleet list task')]
        self.apply(self.worker('fix-login', True))
        self.apply(self.manifest('fix-api', False, urls=('git+https://forge.example/acme/api.git',)))
        self.fleet('reconcile')
        self.fleet('declare', 'fix-login', '--change-request', 'https://github.com/acme/app/pull/7')
        found = lambda q: [l.split()[0] for l in self.sh(search, TEXT=shlex.quote(q)).splitlines()]
        self.assertEqual(found('acme/api'), ['fix-api'])
        self.assertEqual(found('pull/7'), ['fix-login'])
        self.assertEqual(found('reproducer'), [], 'the standing rules are in every brief')
        self.assertEqual(found('vega'), [], 'every child names vega as its parent')
        self.assertEqual(found('it\'s "x"'), [])

    def test_dispatch_writes_only_the_task_specific_brief(self):
        task = self.manifest('fix-login', False, brief='Fix the login redirect.')
        brief = task['spec']['brief']
        self.assertTrue(brief.startswith('Fix the login redirect.'), brief)
        flat = ' '.join(brief.split())
        for rule in ['open it as a draft', 'fleet declare fix-login --change-request URL',
                     '<!-- fleet:worker UID -->', 'fleet get task fix-login', 'never merge',
                     'fleet declare fix-login --json', 'fleet result fix-login --generation',
                     'failing end-to-end reproducer', 'never `fleet send` Mission Control']:
            self.assertIn(rule, flat)
        self.assertNotIn('TASK', brief)
        vega = self.get('vega')
        self.assertEqual(task['metadata']['labels']['gateway.fleet.dev/parent-uid'], vega['metadata']['uid'])
        self.assertEqual(task['metadata']['labels']['vega.fleet.dev/limits'], 'draft-only no-merge')
        self.assertEqual(task['spec']['harness'], vega['spec']['harness'])
        self.assertEqual(task['spec']['env'], {'FLEET_CONFIG': self.env['FLEET_CONFIG']})
        self.assertEqual(task['spec']['workspace'], ['git+https://forge.example/acme/app.git'])
        self.assertIs(task['spec']['dispatch'], False)
        intake = text('.agents/skills/task-intake/SKILL.md')
        for boilerplate in ['fleet:worker', '"kind":"Question"', 'fleet result']:
            self.assertNotIn(boilerplate, intake, 'the shared rules live in briefs/worker.md')
        two = self.manifest('fix-both', True, urls=('git+https://forge.example/acme/app.git',
                                                    'git+https://forge.example/acme/api.git'))
        self.assertEqual(len(two['spec']['workspace']), 2)
        self.apply(two)
        self.fleet('reconcile')
        self.assertEqual(self.get('fix-both')['status']['phase'], 'Briefed')

    def test_local_worker_rules_join_every_brief(self):
        task = self.manifest('fix-login', False)
        self.assertNotIn('cargo', task['spec']['brief'])
        (self.tmp / 'vega-workspace' / 'private').mkdir()
        (self.tmp / 'vega-workspace' / 'private' / 'worker-rules.md').write_text('Build with cargo -j 4.\n')
        task = self.manifest('fix-logout', False)
        self.assertIn('Build with cargo -j 4.', task['spec']['brief'])

    def test_a_long_question_is_read_by_its_id(self):
        self.apply(self.worker('fix-login', True))
        self.fleet('reconcile')
        question = 'Which endpoint? ' + 'context ' * 600
        self.fleet('declare', 'fix-login', '--json', json.dumps({'kind': 'Question', 'id': 'q1', 'text': question}))
        self.fleet('reconcile')
        prompt = text('prompts/mission-control.md')
        read, = [c for c in ' '.join(prompt.split()).split('`')[1::2] if 'select(.id' in c]
        self.assertEqual(self.sh(read, NAME='fix-login', ID='q1').strip(), question.strip())

    def test_every_fleet_command_in_the_guidance_exists(self):
        kinds = [k.lower() for k in json.loads(self.fleet('version', '--json'))['kinds']]
        for asset in GUIDANCE:
            body = text(asset)
            fenced = body.split('```')[1::2]
            inline = ''.join(body.split('```')[0::2]).split('`')[1::2]
            for command in fenced + inline:
                for line in re.findall(r'(?:^|\| |\$\()(fleet [a-z][^|\n)]*)', command, flags=re.M):
                    words = line.split()
                    sub = [w for w in words[1:3] if re.fullmatch(r'[a-z]+', w)]
                    help_text = self.sh(' '.join(['fleet', *sub[:1], '--help']))
                    if len(sub) > 1 and re.search(rf'^\s+{sub[1]}\b', help_text, flags=re.M):
                        help_text = self.sh(' '.join(['fleet', *sub[:2], '--help']))
                    if sub and sub[0] in ('get', 'status', 'list', 'delete', 'label') and len(sub) > 1:
                        self.assertIn(sub[1], kinds, f'{asset}: {line}')
                    elif len(sub) > 1:
                        self.assertRegex(help_text, rf'Usage: fleet {sub[0]} {sub[1]}\b',
                                         f'{asset}: {line}')
                    for flag in re.findall(r'(?<![\w-])(--[a-z][a-z-]*)', line):
                        self.assertIn(flag, help_text, f'{asset}: {line}')
        status = text('.agents/skills/task-status/SKILL.md')
        self.assertIn('fleet send NAME --retry KEY', status)
        self.assertIn('fleet send NAME --drop KEY', status)

    def test_vega_steers_answers_and_amends_from_the_prompt_it_always_reads(self):
        prompt = text('prompts/mission-control.md')
        commands = ' '.join(prompt.split()).split('`')[1::2]
        send, = [c for c in commands if c.startswith('fleet send NAME "')]
        answer, = {c for c in commands if '--answers' in c}
        amend, = {c for c in commands if c.startswith('fleet amend NAME --text')}
        self.assertIn('--if-generation N', commands)
        self.apply(self.worker('fix-login', True))
        self.fleet('reconcile')
        self.fleet('declare', 'fix-login', '--json', '{"kind":"Question","id":"q1","text":"Keep it?"}')
        self.sh(send, NAME='fix-login', TEXT='Prefer the smaller fix')
        self.sh(answer, NAME='fix-login', ID='q1', TEXT='Yes')
        inbox = [e['text'] for e in self.get('fix-login')['status']['inbox']]
        self.assertTrue(any('Prefer the smaller fix' in t for t in inbox), inbox)
        self.assertIn('q1', self.get('fix-login')['status']['answered'])
        generation = self.get('fix-login')['metadata']['generation']
        self.sh(amend, NAME='fix-login', TEXT='Also cover logout', WHY='the user asked')
        self.assertEqual(len(self.get('fix-login')['spec']['amendments']), 1)
        retry = subprocess.run(['bash', '-c', amend.replace('NAME', 'fix-login').replace('TEXT', 'again')
                                .replace('WHY', 'retry') + f' --if-generation {generation}'],
                               env=self.env, cwd=self.tmp, capture_output=True, text=True, timeout=60)
        self.assertEqual(retry.returncode, 5, retry.stderr)
        self.assertEqual(len(self.get('fix-login')['spec']['amendments']), 1)

    def test_a_follow_up_amends_the_existing_task(self):
        intake = text('.agents/skills/task-intake/SKILL.md')
        amend = [b for b in sh_blocks(intake) if b.startswith('fleet amend')]
        self.assertEqual(len(amend), 1, 'task-intake must ship one fleet amend command')
        self.apply(self.worker('fix-login', True))
        self.fleet('reconcile')
        self.fleet('result', 'fix-login', '--generation', '1', '--outcome', 'shipped',
                   '--summary', 'Opened the draft')
        self.fleet('reconcile')
        concluded = self.get('fix-login')
        self.assertEqual(concluded['status']['phase'], 'Concluded')
        digest = sh_blocks(text('.agents/skills/status-digest/SKILL.md'))[0]
        self.assertNotIn('fix-login', self.sh(digest))
        self.sh(amend[0], NAME='fix-login')
        self.assertIn('amended', self.sh(digest))
        self.assertNotIn('result:shipped', self.sh(digest))
        self.fleet('reconcile')
        amended = self.get('fix-login')
        self.assertEqual(amended['status']['phase'], 'Briefed')
        self.assertEqual(amended['status']['brief']['generation'], 2)
        self.assertEqual(amended['status']['session'], concluded['status']['session'])
        self.assertEqual(len(amended['spec']['amendments']), 1)
        self.fleet('result', 'fix-login', '--generation', '2', '--outcome', 'shipped',
                   '--summary', 'Covered the follow-up')
        self.fleet('reconcile')
        self.assertEqual(self.get('fix-login')['status']['phase'], 'Concluded')
        self.assertNotIn('fix-login', self.sh(digest))


if __name__ == '__main__':
    unittest.main()
