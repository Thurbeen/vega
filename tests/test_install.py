"""End to end: ./install.sh puts VEGA into a sandboxed Fleet v3 and takes it out.

Every run gets its own HOME and a PATH that holds only the tools the installer
may use, so the real ~/.config/fleet is never read and the harness check sees
only the stub agents a test puts there. The Fleet store runs the fake runtime:
no agent starts.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ['sh', 'bash', 'env', 'cat', 'grep', 'sed', 'mkdir', 'mv', 'cp', 'rm', 'dirname',
         'basename', 'tr', 'head', 'tail', 'mktemp', 'printf', 'uname', 'chmod', 'cmp', 'ls']
PS_FLAGS = {'--config': '-Config', '--harness': '-Harness', '--uninstall': '-Uninstall'}



class Sandbox:
    """A HOME, a PATH and a fake-runtime Fleet config, all under one temp dir."""

    def __init__(self, case, fleet=None, jq=True, agents=('codex',)):
        self.case = case
        self.dir = Path(tempfile.mkdtemp(prefix='vega-test-', dir=ROOT))
        case.addCleanup(shutil.rmtree, self.dir)
        self.home = self.dir / 'home'
        self.home.mkdir()
        self.bin = self.dir / 'bin'
        self.bin.mkdir()
        for tool in TOOLS:
            found = shutil.which(tool)
            if found:
                (self.bin / tool).symlink_to(found)
        if case.installer == 'install.ps1':
            (self.bin / 'pwsh').symlink_to(shutil.which('pwsh'))
        if jq:
            (self.bin / 'jq').symlink_to(shutil.which('jq'))
        if fleet is None:
            (self.bin / 'fleet').symlink_to(case.fleet)
        else:
            self.script('fleet', fleet)
        for agent in agents:
            self.script(agent, 'exit 0')
        self.config = self.dir / 'conf' / 'fleet.toml'
        self.config.parent.mkdir()
        self.config.write_text('version = 1\n\n[data]\ndir = "data"\n\n'
                               '[runtime]\nkind = "fake"\ndir = "fake-host"\n')

    def script(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)

    def env(self, **extra):
        env = {'HOME': str(self.home), 'PATH': str(self.bin), 'LANG': 'C.UTF-8'}
        env.update(extra)
        return env

    def run(self, *args, env=None, check=True):
        if self.case.installer == 'install.ps1':
            command = ['pwsh', '-NoProfile', '-NonInteractive', '-File', str(ROOT / 'install.ps1'),
                       *[PS_FLAGS.get(a, a) for a in args]]
        else:
            command = [str(ROOT / 'install.sh'), *args]
        result = subprocess.run(command, text=True, capture_output=True, timeout=120,
                                env=env or self.env(), cwd=self.dir)
        if check:
            self.case.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def fleet(self, *args, config=None, check=True):
        result = subprocess.run([str(self.case.fleet), '--config', str(config or self.config), *args],
                                text=True, capture_output=True, timeout=60, env=self.env(),
                                cwd=self.dir)
        if check:
            self.case.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def task(self, config=None):
        result = subprocess.run([str(self.case.fleet), '--config', str(config or self.config),
                                 'get', 'task', 'vega'], text=True, capture_output=True,
                                timeout=60, env=self.env(), cwd=self.dir)
        return json.loads(result.stdout) if result.returncode == 0 else None


class Install(unittest.TestCase):
    installer = 'install.sh'

    def setUp(self):
        fleet = os.environ.get('FLEET_BIN')
        self.assertTrue(fleet, 'Set FLEET_BIN to a Fleet v3 binary; integration is required')
        self.fleet = Path(fleet).resolve()
        version = json.loads(subprocess.run([str(self.fleet), 'version', '--json'], text=True,
                                            capture_output=True, check=True).stdout)
        self.assertGreaterEqual(version.get('runtimeProtocol') or 0, 2, 'FLEET_BIN is not Fleet v3')
        self.assertTrue(shutil.which('jq'), 'the installer needs jq')

    def test_install_applies_a_valid_vega_task_and_it_starts(self):
        box = Sandbox(self)
        out = box.run('--config', str(box.config), '--harness', 'codex').stdout
        vega = box.task()
        self.assertIsNotNone(vega, out)
        spec = vega['spec']
        self.assertEqual(spec['harness'], 'codex')
        self.assertEqual(spec['workspace'], [(ROOT / 'workspace').as_uri()])
        self.assertEqual(spec['env'], {'FLEET_CONFIG': str(box.config)})
        self.assertTrue(spec['dispatch'])
        self.assertIn('Mission Control', spec['brief'])
        # The fake runtime takes it to Briefed in VEGA's own workspace.
        box.fleet('reconcile')
        status = box.task()['status']
        self.assertEqual(status['phase'], 'Briefed', status)
        self.assertEqual(status['workspace']['dirs'], [str(ROOT / 'workspace')])
        # The installer says how to reach VEGA.
        self.assertIn('fleet send vega', out)
        self.assertIn('thurbox', out)

    def test_a_second_run_changes_nothing(self):
        box = Sandbox(self)
        box.run('--config', str(box.config), '--harness', 'codex')
        first = box.task()
        config = box.config.read_bytes()
        out = box.run('--config', str(box.config), '--harness', 'codex').stdout
        again = box.task()
        self.assertEqual(again['metadata']['uid'], first['metadata']['uid'])
        self.assertEqual(again['metadata']['generation'], first['metadata']['generation'])
        self.assertEqual(box.config.read_bytes(), config)
        self.assertIn('already installed', out)

    def test_fleet_config_selects_the_store(self):
        box = Sandbox(self)
        box.run('--harness', 'codex', env=box.env(FLEET_CONFIG=str(box.config)))
        self.assertEqual(box.task()['spec']['env'], {'FLEET_CONFIG': str(box.config)})

    def test_without_a_config_fleet_init_writes_the_native_one(self):
        box = Sandbox(self)
        box.run('--harness', 'codex')
        native = box.home / '.config' / 'fleet' / 'config.toml'
        self.assertTrue(native.is_file())
        vega = box.task(config=native)
        self.assertIsNotNone(vega)
        self.assertEqual(vega['spec']['env'], {'FLEET_CONFIG': str(native)})

    def test_the_harness_defaults_to_one_on_path(self):
        box = Sandbox(self, agents=('opencode',))
        box.run('--config', str(box.config))
        self.assertEqual(box.task()['spec']['harness'], 'opencode')

    def test_a_harness_fleet_does_not_know_is_refused(self):
        box = Sandbox(self)
        result = box.run('--config', str(box.config), '--harness', 'nope', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('nope', result.stderr)
        self.assertIsNone(box.task())

    def test_a_harness_missing_from_path_is_refused(self):
        box = Sandbox(self, agents=())
        result = box.run('--config', str(box.config), '--harness', 'codex', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('codex', result.stderr)
        self.assertIsNone(box.task())

    def test_fleet_v2_is_refused(self):
        v2 = json.dumps({'version': '2.23.1', 'apiVersions': ['fleet/v1alpha1'], 'configVersion': 1})
        box = Sandbox(self, fleet=f"[ \"$1\" = version ] && echo '{v2}' && exit 0\nexit 1")
        result = box.run('--config', str(box.config), '--harness', 'codex', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Fleet v3', result.stderr)

    def test_missing_jq_is_reported(self):
        box = Sandbox(self, jq=False)
        result = box.run('--config', str(box.config), '--harness', 'codex', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('jq', result.stderr)

    def test_forge_hosts_are_added_for_the_forge_clis_on_path(self):
        box = Sandbox(self, agents=('codex', 'gh'))
        out = box.run('--config', str(box.config), '--harness', 'codex').stdout
        self.assertIn('"github.com" = { kind = "github", cli = "gh" }', box.config.read_text())
        self.assertIn('github.com', out)
        # A worker can now declare the change it opens.
        box.fleet('reconcile')
        box.fleet('declare', 'vega', '--change-request', 'https://github.com/o/r/pull/1')

    def test_configured_forge_hosts_are_left_alone(self):
        box = Sandbox(self, agents=('codex', 'gh'))
        with box.config.open('a') as f:
            f.write('\n[forge.hosts]\n"gitlab.com" = { kind = "gitlab", cli = "glab" }\n')
        before = box.config.read_bytes()
        box.run('--config', str(box.config), '--harness', 'codex')
        self.assertEqual(box.config.read_bytes(), before)

    def test_another_harness_on_an_installed_vega_is_refused(self):
        box = Sandbox(self, agents=('codex', 'opencode'))
        box.run('--config', str(box.config), '--harness', 'codex')
        result = box.run('--config', str(box.config), '--harness', 'opencode', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('uninstall', result.stderr.lower())
        self.assertEqual(box.task()['spec']['harness'], 'codex')

    def test_uninstall_deletes_the_task_and_is_idempotent(self):
        box = Sandbox(self)
        box.run('--config', str(box.config), '--harness', 'codex')
        box.fleet('reconcile')
        box.run('--uninstall', '--config', str(box.config))
        # The finalizer holds the record until fleet up releases the session,
        # which a fake session never lets go of.
        self.assertIsNotNone(box.task()['metadata'].get('deletionTimestamp'))
        self.assertTrue((ROOT / 'workspace' / 'AGENTS.md').is_file(), 'uninstall keeps the files')
        box.run('--uninstall', '--config', str(box.config))
        result = box.run('--config', str(box.config), '--harness', 'codex', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('being deleted', result.stderr)

    def test_uninstall_without_vega_does_nothing(self):
        box = Sandbox(self)
        out = box.run('--uninstall', '--config', str(box.config)).stdout
        self.assertIn('not installed', out)
        self.assertFalse((box.home / '.config').exists())

class InstallPowerShell(Install):
    """The same contract for install.ps1, where PowerShell 7 is on PATH."""

    installer = 'install.ps1'

    def setUp(self):
        if not shutil.which('pwsh'):
            self.skipTest('pwsh is not on PATH')
        super().setUp()


if __name__ == '__main__':
    unittest.main()
