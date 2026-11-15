# Install VEGA into a Fleet v3 store as the Task `vega`, or take it out.
# Safe to run again: it changes only what is missing. Mirrors install.sh.
param(
    [string]$Config,
    [string]$Harness,
    [switch]$Uninstall,
    [switch]$Help
)
$ErrorActionPreference = 'Stop'

if ($Help) {
    @'
Usage: ./install.ps1 [-Config PATH] [-Harness NAME]
       ./install.ps1 -Uninstall [-Config PATH]

  -Config PATH   Fleet config to install into (else FLEET_CONFIG, then
                 Fleet's per-user config, which `fleet init` writes if absent)
  -Harness NAME  The coding agent VEGA runs (default: the first one
                 `fleet doctor` finds on PATH)
  -Uninstall     Delete the Task `vega`; this checkout and its files stay
'@
    exit 0
}

function Die([string]$Message) {
    [Console]::Error.WriteLine("install.ps1: $Message")
    exit 1
}

# Runs fleet; returns its exit code and its output as one string.
function Fleet([string[]]$Arguments, [string]$Stdin) {
    $info = [System.Diagnostics.ProcessStartInfo]::new($script:fleet)
    foreach ($a in $Arguments) { $info.ArgumentList.Add($a) }
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $p = [System.Diagnostics.Process]::Start($info)
    if ($Stdin) { $p.StandardInput.Write($Stdin) }
    $p.StandardInput.Close()
    $err = $p.StandardError.ReadToEndAsync()
    $out = $p.StandardOutput.ReadToEnd()
    $p.WaitForExit()
    [pscustomobject]@{ Code = $p.ExitCode; Out = $out; Err = $err.Result }
}

$here = $PSScriptRoot
$fleetCmd = Get-Command fleet -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $fleetCmd) { Die 'fleet is not on PATH: install Fleet v3 first (see README.md)' }
$script:fleet = $fleetCmd.Source
if (-not (Get-Command jq -CommandType Application -ErrorAction SilentlyContinue)) {
    Die "jq is not on PATH: install jq; VEGA's skills use it too"
}

$r = Fleet @('version', '--json')
if ($r.Code -ne 0) { Die 'fleet version --json failed: install Fleet v3' }
try { $version = $r.Out | ConvertFrom-Json } catch { $version = $null }
if (-not $version -or -not ($version.runtimeProtocol -ge 2) -or
    $version.apiVersions -notcontains 'fleet/v1alpha1' -or $version.kinds -notcontains 'Task') {
    $v = if ($version.version) { $version.version } else { 'unknown' }
    Die "$script:fleet is not Fleet v3 ($v): install Fleet v3 (see README.md)"
}

# Fleet's own selection: -Config, then FLEET_CONFIG, then the per-user file.
$named = if ($Config) { $Config } elseif ($env:FLEET_CONFIG) { $env:FLEET_CONFIG } else { '' }
if ($named) {
    $Config = $named
} elseif ($IsWindows -or $env:OS -eq 'Windows_NT') {
    $Config = Join-Path $env:APPDATA 'fleet\config.toml'
} elseif ($env:XDG_CONFIG_HOME) {
    $Config = Join-Path $env:XDG_CONFIG_HOME 'fleet/config.toml'
} else {
    $Config = Join-Path $HOME '.config/fleet/config.toml'
}
$Config = [System.IO.Path]::GetFullPath($Config, (Get-Location).Path)

function Get-Vega {
    $r = Fleet @('--config', $Config, 'get', 'task', 'vega')
    if ($r.Code -eq 0) { return $r.Out | ConvertFrom-Json }
    if ($r.Code -eq 3) { return $null }
    Die $r.Err.Trim()
}

if ($Uninstall) {
    if (-not (Test-Path -LiteralPath $Config -PathType Leaf) -or -not (Get-Vega)) {
        Write-Output "VEGA is not installed in $Config."
        exit 0
    }
    $r = Fleet @('--config', $Config, 'delete', 'task', 'vega')
    if ($r.Code -ne 0) { Die $r.Err.Trim() }
    Write-Output "Deleted the Task vega from ${Config}: fleet up releases its session."
    Write-Output 'Its worker Tasks keep running; this checkout stays.'
    exit 0
}

$r = if ($named) { Fleet @('--config', $Config, 'init') } else { Fleet @('init') }
if ($r.Code -ne 0) { Die ($r.Out + $r.Err).Trim() }

$doctor = $null
try { $doctor = (Fleet @('--config', $Config, 'doctor', '--json')).Out | ConvertFrom-Json } catch {}
$harnessChecks = @($doctor.checks | Where-Object { $_.area -eq 'harness' })
if (-not $Harness) {
    $Harness = ($harnessChecks | Where-Object { $_.level -eq 'ok' } | Select-Object -First 1).name
    if (-not $Harness) { Die 'no coding agent found on PATH: install and log in to one, or pass -Harness' }
}
if ($version.harnesses -notcontains $Harness) {
    Die "Fleet has no harness '$Harness'; it knows: $($version.harnesses -join ', ')"
}
$missing = $harnessChecks | Where-Object { $_.name -eq $Harness -and $_.level -ne 'ok' } | Select-Object -First 1
if ($missing) {
    $hint = if ($missing.hint) { ": $($missing.hint)" } else { '' }
    Die "harness ${Harness}: $($missing.detail)$hint"
}

# Workers declare the changes they open; Fleet follows a change only on a
# forge host the config names. Add the hosts whose CLI is here, once.
$added = @()
if (-not (Select-String -LiteralPath $Config -Pattern '^\s*(\[forge\.hosts|hosts\s*=|forge\.hosts)' -Quiet)) {
    $hosts = ''
    foreach ($h in @(@('github.com', 'github', 'gh'), @('gitlab.com', 'gitlab', 'glab'))) {
        if (Get-Command $h[2] -CommandType Application -ErrorAction SilentlyContinue) {
            $hosts += "`"$($h[0])`" = { kind = `"$($h[1])`", cli = `"$($h[2])`" }`n"
            $added += $h[0]
        }
    }
    if ($hosts) {
        $candidate = "$Config.vega.$PID"
        Copy-Item -LiteralPath $Config -Destination $candidate
        [System.IO.File]::AppendAllText($candidate, "`n[forge.hosts]`n$hosts")
        $r = Fleet @('--config', $candidate, 'list', 'task', '--json')
        if ($r.Code -ne 0) {
            Remove-Item -LiteralPath $candidate
            Die "adding [forge.hosts] to $Config failed: $($r.Err.Trim())"
        }
        Move-Item -LiteralPath $candidate -Destination $Config -Force
    }
}

$workspaceDir = Join-Path $here 'workspace'
$manifest = Get-Content -Raw -LiteralPath (Join-Path $here 'tasks/vega.json') | ConvertFrom-Json
$manifest.spec.harness = $Harness
$manifest.spec.workspace = @([System.Uri]::new($workspaceDir, [System.UriKind]::Absolute).AbsoluteUri)
$manifest.spec | Add-Member -NotePropertyName env -NotePropertyValue ([ordered]@{ FLEET_CONFIG = $Config }) -Force

$vega = Get-Vega
if ($vega) {
    if ($vega.metadata.deletionTimestamp) { Die 'VEGA is being deleted: run this again once fleet up has released it' }
    $differs = @('harness', 'workspace', 'env') | Where-Object {
        ($vega.spec.$_ | ConvertTo-Json -Compress -Depth 5) -ne ($manifest.spec.$_ | ConvertTo-Json -Compress -Depth 5)
    }
    if ($differs) { Die "VEGA is installed with another $($differs -join ', '): run ./install.ps1 -Uninstall first" }
    if (-not $vega.spec.dispatch) {
        $vega.spec.dispatch = $true
        $vega.PSObject.Properties.Remove('status')
        $r = Fleet @('--config', $Config, 'apply', '-f', '-') ($vega | ConvertTo-Json -Depth 20)
        if ($r.Code -ne 0) { Die $r.Err.Trim() }
    }
    Write-Output "VEGA is already installed in $Config."
} else {
    $r = Fleet @('--config', $Config, 'apply', '-f', '-', '--create-only') ($manifest | ConvertTo-Json -Depth 20)
    if ($r.Code -ne 0) { Die $r.Err.Trim() }
    Write-Output "Installed VEGA in ${Config}: the Task vega runs $Harness in $workspaceDir."
}
if ($added) { Write-Output "Added forge hosts to the config: $($added -join ' ')." }

Write-Output ''
Write-Output 'Talk to VEGA:'
if ($named) { Write-Output "  `$env:FLEET_CONFIG = '$Config'" }
Write-Output '  thurbox                       # VEGA is the session vega'
Write-Output '  fleet send vega "MESSAGE"     # or queue a message for it'
$held = $false
try { $held = ((Fleet @('--config', $Config, 'version', '--json')).Out | ConvertFrom-Json).manager.held -eq $true } catch {}
if ($held) {
    if ($added) { Write-Output 'Restart fleet up to follow changes on the new forge hosts.' }
} else {
    Write-Output 'Fleet is not running: thurbox starts it, or run fleet up.'
}
