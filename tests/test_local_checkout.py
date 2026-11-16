import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTAKE = ROOT / 'workspace/.agents/skills/task-intake/SKILL.md'


def workspace_section():
    body = INTAKE.read_text()
    return body.split('\n## Workspace\n', 1)[1].split('\n## ', 1)[0]


def workspace_git():
    fleet = os.environ.get('FLEET_BIN')
    beside = Path(fleet).resolve().parent / 'workspace-git' if fleet else None
    found = str(beside) if beside and beside.exists() else shutil.which('workspace-git')
    return found


class LocalCheckout(unittest.TestCase):
    def setUp(self):
        self.tool = workspace_git()
        self.assertTrue(self.tool, 'workspace-git ships beside FLEET_BIN; integration is required')
        self.tmp = Path(tempfile.mkdtemp(prefix='vega-test-checkout-', dir=ROOT))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update({'HOME': str(self.tmp), 'GIT_CONFIG_NOSYSTEM': '1',
                         'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid',
                         'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.invalid'})

    def git(self, cwd, *args):
        result = subprocess.run(['git', '-C', str(cwd), *args], text=True, capture_output=True,
                                env=self.env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def stale_checkout(self):
        upstream = self.tmp / 'upstream.git'
        self.git(self.tmp, 'init', '-q', '--bare', '-b', 'main', str(upstream))
        seed = self.tmp / 'seed'
        self.git(self.tmp, 'clone', '-q', str(upstream), str(seed))
        self.git(seed, 'commit', '-q', '--allow-empty', '-m', 'first')
        self.git(seed, 'push', '-q', 'origin', 'HEAD:main')
        checkout = self.tmp / 'checkout'
        self.git(self.tmp, 'clone', '-q', str(upstream), str(checkout))
        self.git(seed, 'commit', '-q', '--allow-empty', '-m', 'second')
        self.git(seed, 'push', '-q', 'origin', 'HEAD:main')
        return checkout, self.git(seed, 'rev-parse', 'HEAD')

    def make(self, key, url):
        request = json.dumps({'root': str(self.tmp / 'workspaces'), 'key': key, 'urls': [url]})
        result = subprocess.run([self.tool, 'make'], input=request, text=True, capture_output=True,
                                env=self.env, timeout=60)
        answer = json.loads(result.stdout)
        self.assertIn('made', answer, result.stdout + result.stderr)
        return answer['made']['dirs'][0]

    def test_a_mapped_repository_is_named_by_its_local_checkout(self):
        flat = ' '.join(workspace_section().split())
        self.assertIn('private/INSTRUCTIONS.md', flat)
        self.assertRegex(flat, r'(?i)prefer[^.]*local checkout', 'a local checkout comes first')
        self.assertRegex(flat, r'(?i)otherwise[^.]*`git\+https://', 'git+https is the fallback')

    def test_the_local_checkout_urls_task_intake_ships_start_from_the_upstream_now(self):
        section = workspace_section()
        local = re.search(r'`(git\+file:///abs/checkout)`', section).group(1)
        remote_branch = re.search(r'`(#origin/[a-z]+)`', section).group(1)
        checkout, upstream_head = self.stale_checkout()
        stale_main = self.git(checkout, 'rev-parse', 'main')
        self.assertNotEqual(stale_main, upstream_head)
        url = local.replace('/abs/checkout', str(checkout))
        for key, written in [('default.u1', url), ('branch.u2', url + remote_branch)]:
            with self.subTest(written=written):
                worktree = self.make(key, written)
                self.assertEqual(self.git(worktree, 'rev-parse', 'HEAD'), upstream_head)
        local_branch = self.make('local.u3', url + remote_branch.replace('origin/', ''))
        self.assertEqual(self.git(local_branch, 'rev-parse', 'HEAD'), stale_main,
                         'a bare branch ref names the stale local branch the guidance warns about')
        self.assertEqual(self.git(checkout, 'rev-parse', 'main'), stale_main,
                         "the user's own branch is left as it was")


if __name__ == '__main__':
    unittest.main()
