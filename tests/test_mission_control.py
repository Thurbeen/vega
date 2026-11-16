"""VEGA's guidance, run against the real Fleet v3 binary with the fake runtime.

./install.sh puts VEGA into a sandboxed store, then each check runs the
commands the installed guidance ships: a worker reports back through VEGA's
inbox, the status digest rebuilds the working state from Fleet, and
re-hydration is one ordinary inbox delivery. They cannot prove a model obeys
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
            '.agents/skills/task-status/SKILL.md', '.agents/skills/status-digest/SKILL.md']


def text(asset):
    return (WORKSPACE / asset).read_text()


def sh_blocks(body):
    """The shell commands a skill or prompt ships, in order."""
    return [block.split('```', 1)[0].strip() for block in body.split('```sh\n')[1:]]


def text_blocks(body):
    return [block.split('```', 1)[0].strip() for block in body.split('```text\n')[1:]]


def section(body, heading):
    return body.split(f'\n## {heading}\n', 1)[1].split('\n## ', 1)[0]


def json_blocks(body):
    return [json.loads(block.split('```', 1)[0]) for block in body.split('```json\n')[1:]]


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

    def sh(self, command, **subst):
        for key, value in subst.items():
            command = command.replace(key, value)
        result = subprocess.run(['bash', '-euo', 'pipefail', '-c', command], text=True,
                                capture_output=True, timeout=60, env=self.env, cwd=self.tmp)
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

    def worker(self, name, dispatch, **labels):
        """The task-intake example, as VEGA fills it in for one request."""
        intake = text('.agents/skills/task-intake/SKILL.md')
        task = next(t for t in json_blocks(intake) if t['kind'] == 'Task' and 'labels' in t['metadata'])
        task['metadata']['name'] = name
        uid_command = re.search(r'`(fleet get task vega \| jq -r \.metadata\.uid)`', intake).group(1)
        uid = self.sh(uid_command).strip()
        task['metadata']['labels'] = {key: uid if value == 'VEGA_UID' else value
                                      for key, value in task['metadata']['labels'].items()}
        task['metadata']['labels'].update(labels)
        task['spec']['env']['FLEET_CONFIG'] = self.env['FLEET_CONFIG']
        task['spec']['harness'] = self.get('vega')['spec']['harness']
        task['spec']['dispatch'] = dispatch
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

    def test_every_example_resource_applies(self):
        examples = [r for a in GUIDANCE for r in json_blocks(text(a))]
        self.assertGreaterEqual(len(examples), 3)
        for resource in examples:
            resource = json.loads(json.dumps(resource).replace('VEGA_UID', self.get('vega')['metadata']['uid']))
            resource.setdefault('spec', {})
            if resource['kind'] == 'Task':
                resource['spec']['dispatch'] = False
            self.apply(resource)

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
        # Serial lanes, limits, open questions and change ownership live on
        # the Tasks, so a cleared or restarted VEGA reads them back from Fleet.
        digest_skill = text('.agents/skills/status-digest/SKILL.md')
        digest, set_label, release = sh_blocks(digest_skill)[:3]
        self.apply(self.worker('fix-login', True, **{'vega.fleet.dev/limits': 'draft-only no-merge'}))
        self.apply(self.worker('fix-logout', False, **{'vega.fleet.dev/after': 'fix-login'}))
        self.fleet('reconcile')
        self.fleet('declare', 'fix-login', '--json',
                   '{"kind":"Question","id":"q1","text":"Keep the old endpoint?"}')
        board = self.sh(digest).splitlines()
        self.assertEqual(len(board), 2, board)
        lines = {line.split()[0]: line for line in board}
        self.assertNotIn('vega', lines)
        self.assertIn('limits:draft-only no-merge', lines['fix-login'])
        # The workspace shows which live Tasks overlap or own a follow-up.
        self.assertIn('ws:git+https://forge.example/acme/app.git', lines['fix-login'])
        self.assertIn('ask:q1', lines['fix-login'])
        self.assertIn('held', lines['fix-logout'])
        self.assertIn('after:fix-login', lines['fix-logout'])
        self.assertNotIn('{', '\n'.join(board), 'the digest must not dump JSON')
        # A failed or stuck predecessor must not start the rest of its lane.
        for body in [digest_skill, text('prompts/mission-control.md')]:
            self.assertIn('verified `shipped`', ' '.join(body.split()))
        self.fleet('send', 'fix-login', '--answers', 'q1', 'Yes')
        self.sh(set_label, NAME='fix-logout')
        self.assertIn('needs:', self.sh(digest))
        self.assertNotIn('ask:q1', self.sh(digest))
        # An empty value clears a label from the board.
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

    def test_vega_rehydrates_through_its_own_inbox_without_a_clear(self):
        prompt = text('prompts/mission-control.md')
        blocks = sh_blocks(prompt)
        self.assertFalse([b for b in blocks if '/clear' in b], 'mission-control must not queue /clear')
        self.assertIn('never queue one in reply to a re-hydrate', ' '.join(prompt.split()).lower())
        rehydrate = [b for b in blocks if 'VEGA re-hydrate' in b]
        self.assertEqual(len(rehydrate), 1, 'mission-control must ship one re-hydrate block')
        self.sh(rehydrate[0])
        inbox = [entry['text'] for entry in self.get('vega')['status']['inbox']]
        self.assertEqual(len(inbox), 1, inbox)
        self.assertIn('prompts/mission-control.md', inbox[0])
        self.fleet('reconcile')
        self.assertFalse(self.get('vega')['status'].get('inbox'))

    def sh_status(self, command, **subst):
        for key, value in subst.items():
            command = command.replace(key, value)
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', command], text=True,
                              capture_output=True, timeout=60, env=self.env, cwd=self.tmp)

    def publish_milestone(self, milestone, data='{"url":"https://forge.example/acme/app/pull/7"}'):
        brief_lines = text_blocks(section(text('.agents/skills/task-intake/SKILL.md'), 'Board milestones'))
        publish = [line for block in brief_lines for line in block.splitlines()
                   if line.startswith('fleet event publish')]
        self.assertEqual(len(publish), 1, 'the brief lines must carry one publish command')
        self.sh(publish[0].replace("'{\"url\":\"URL\"}'", shlex.quote(data)),
                MILESTONE=milestone, SUBJECT='acme/app', NAME='fix-login')

    def test_every_brief_carries_the_board_milestones(self):
        intake = text('.agents/skills/task-intake/SKILL.md')
        lines = text_blocks(section(intake, 'Board milestones'))
        self.assertEqual(len(lines), 1, 'one block of brief lines to copy into every brief')
        flat = ' '.join(lines[0].split())
        for milestone in ['task.started', 'task.question', 'task.pr.opened', 'task.ci.green', 'task.result']:
            self.assertIn(milestone, flat)
        for required in ['best effort', 'never blocks the work', 'never secrets or brief text',
                         '--subject SUBJECT', '--correlation NAME', '--key NAME-MILESTONE']:
            self.assertIn(required, flat)
        self.assertLessEqual(len(lines[0].splitlines()), 6, 'keep the brief lines short')
        self.assertIn('Board milestones', ' '.join(section(intake, 'Manifest').split()))
        self.publish_milestone('started', '{}')
        self.publish_milestone('pr.opened')
        self.publish_milestone('pr.opened')
        events = json.loads(self.fleet('event', 'list', '--correlation', 'fix-login', '--json'))
        self.assertEqual([e['type'] for e in events], ['task.started', 'task.pr.opened'],
                         'a retried publish under one key appends nothing')
        self.assertEqual(events[1]['subject'], 'acme/app')
        self.assertEqual(events[1]['key'], 'fix-login-pr.opened')

    def test_status_reads_the_board_as_claims(self):
        status = text('.agents/skills/task-status/SKILL.md')
        digest_skill = text('.agents/skills/status-digest/SKILL.md')
        for body in [status, digest_skill]:
            flat = ' '.join(section(body, 'Timeline').split())
            for required in ['claim', 'not evidence', 'Board/shared not found', 'exit 5', 'Expired',
                             'never create']:
                self.assertIn(required, flat)
        self.assertIn('timeline', ' '.join(text('prompts/mission-control.md').split()).lower())
        one = [b for b in sh_blocks(section(status, 'Timeline')) if 'fleet event list' in b]
        every = [b for b in sh_blocks(section(digest_skill, 'Timeline')) if 'fleet event list' in b]
        self.assertEqual((len(one), len(every)), (1, 1))
        self.assertIn("--correlation NAME", one[0])
        self.assertIn('--after SEQ', every[0])
        head = re.search(r'`(fleet get board shared \| jq [^`]+)`', digest_skill).group(1)
        self.assertEqual(self.sh(head).strip(), '0')
        self.publish_milestone('pr.opened')
        self.assertIn('task.pr.opened', self.sh(one[0], NAME='fix-login'))
        self.assertEqual(self.sh(head).strip(), '1')
        timeline = self.sh(every[0], SEQ='0').splitlines()
        self.assertEqual(timeline, ['1  fix-login  task.pr.opened  https://forge.example/acme/app/pull/7'])
        self.assertEqual(self.sh(every[0], SEQ='1'), '')
        # Retention dropped the events after the cursor: the reader is told
        # where the log resumes, through the pipe.
        self.apply({'apiVersion': 'fleet/v1alpha1', 'kind': 'Board', 'metadata': {'name': 'shared'},
                    'spec': {'retention': {'maxCount': 1}}})
        self.publish_milestone('ci.green', '{}')
        self.publish_milestone('result', '{"outcome":"shipped"}')
        expired = self.sh_status(every[0], SEQ='0')
        self.assertEqual(expired.returncode, 5, expired.stderr)
        self.assertIn('expired: list again with --after 2', expired.stdout)
        self.fleet('delete', 'board', 'shared')
        missing = self.sh_status(one[0], NAME='fix-login')
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('Board/shared not found', missing.stderr)

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
        self.assertIn('result:shipped', self.sh(digest))
        self.sh(amend[0], NAME='fix-login')
        # Fleet keeps the old result until the worker answers the amendment,
        # so the board must not show the follow-up as done.
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
        self.assertIn('result:shipped', self.sh(digest))
        self.assertNotIn('amended', self.sh(digest))


if __name__ == '__main__':
    unittest.main()
