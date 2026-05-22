#!/usr/bin/env node
import {
  cdpPort,
  exitFromResult,
  parseCliArgs,
  parseInteger,
  powershellEncoded,
  psQuote,
} from './lib.mjs';

const actions = new Set(['ensure', 'status', 'stop', 'check-chrome']);

const { positionals, values } = parseCliArgs({
  options: {
    port: { type: 'string' },
    profile: { type: 'string' },
    'timeout-seconds': { type: 'string' },
  },
});

const [action = 'ensure'] = positionals;
if (!actions.has(action)) {
  console.error(`Unknown action: ${action}`);
  process.exit(2);
}

const port = parseInteger(values.port ?? String(cdpPort), '--port');
const timeoutSeconds = parseInteger(
  values['timeout-seconds'] ?? process.env.WINDOWS_CHROME_START_TIMEOUT_SECONDS ?? '15',
  '--timeout-seconds',
);
const profilePath = values.profile ?? process.env.WINDOWS_CHROME_PROFILE_PATH ?? '';

const script = `
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Action = ${psQuote(action)}
$Port = ${port}
$ProfilePathOverride = ${psQuote(profilePath)}
$TimeoutSeconds = ${timeoutSeconds}
if ($ProfilePathOverride) {
  $ProfilePath = $ProfilePathOverride
} else {
  $ProfilePath = Join-Path $env:LOCALAPPDATA 'Codex\\playwright-wsl\\profile'
}

function Write-Fail([string] $Message) {
  Write-Error $Message
  exit 1
}

function Get-ChromePath {
  $candidates = @(
    (Join-Path $env:ProgramFiles 'Google\\Chrome\\Application\\chrome.exe'),
    (Join-Path \${env:ProgramFiles(x86)} 'Google\\Chrome\\Application\\chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google\\Chrome\\Application\\chrome.exe')
  )

  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path $candidate)) {
      return $candidate
    }
  }

  $command = Get-Command chrome.exe -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  return $null
}

function Test-TcpPort {
  try {
    $client = [Net.Sockets.TcpClient]::new()
    $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne(500)) {
      $client.Close()
      return $false
    }
    $client.EndConnect($async)
    $client.Close()
    return $true
  } catch {
    return $false
  }
}

function Test-Cdp {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 2
    return $response.StatusCode -eq 200 -and $response.Content -match '"Browser"\\s*:\\s*"Chrome/'
  } catch {
    return $false
  }
}

function Get-ChromeProcesses {
  @(Get-CimInstance Win32_Process -Filter "name = 'chrome.exe'" -ErrorAction SilentlyContinue)
}

function Uses-Port($Process) {
  $cmd = $Process.CommandLine
  if ($null -eq $cmd) {
    $cmd = ""
  }
  $cmd = $cmd.ToLowerInvariant()
  return $cmd.Contains("--remote-debugging-port=$Port")
}

function Uses-Profile($Process) {
  $cmd = $Process.CommandLine
  if ($null -eq $cmd) {
    $cmd = ""
  }
  $cmd = $cmd.ToLowerInvariant()
  $profile = $ProfilePath.ToLowerInvariant()
  return $cmd.Contains($profile)
}

function Get-SkillProcesses {
  @(Get-ChromeProcesses | Where-Object { (Uses-Port $_) -and (Uses-Profile $_) })
}

function Get-PortProcesses {
  @(Get-ChromeProcesses | Where-Object { Uses-Port $_ })
}

function Get-ProfileProcesses {
  @(Get-ChromeProcesses | Where-Object { Uses-Profile $_ })
}

function Stop-SkillChrome {
  $targets = @(Get-ProfileProcesses)
  foreach ($process in $targets) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
  }
  if ($targets.Count -gt 0) {
    Start-Sleep -Milliseconds 500
  }
  return $targets.Count
}

function Assert-PortOwnership {
  $cdpHealthy = Test-Cdp
  $skillProcesses = @(Get-SkillProcesses)
  $portProcesses = @(Get-PortProcesses)

  if ($cdpHealthy -and $skillProcesses.Count -gt 0) {
    return
  }

  if ($cdpHealthy -and $skillProcesses.Count -eq 0) {
    Write-Fail "Port $Port responds as Chrome CDP but is not owned by this skill profile: $ProfilePath"
  }

  if ($portProcesses.Count -gt 0 -and $skillProcesses.Count -eq 0) {
    Write-Fail "Port $Port is used by a Chrome process that is not this skill profile: $ProfilePath"
  }

  if ((Test-TcpPort) -and $skillProcesses.Count -eq 0) {
    Write-Fail "Port $Port is already open but is not owned by this skill. Choose another WINDOWS_CHROME_CDP_PORT."
  }
}

function Start-SkillChrome {
  $chrome = Get-ChromePath
  if (-not $chrome) {
    Write-Fail "Google Chrome was not found on Windows. Install Chrome or add chrome.exe to PATH, then retry."
  }

  New-Item -ItemType Directory -Force -Path $ProfilePath | Out-Null

  $args = @(
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=$Port",
    "--user-data-dir=$ProfilePath",
    "--no-first-run",
    "--no-default-browser-check",
    "about:blank"
  )

  Start-Process -FilePath $chrome -ArgumentList $args | Out-Null

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Cdp) {
      return
    }
    Start-Sleep -Milliseconds 250
  }

  Write-Fail "Started Chrome but CDP did not become healthy at http://127.0.0.1:$Port/json/version"
}

if ($Action -eq "check-chrome") {
  $chrome = Get-ChromePath
  if (-not $chrome) {
    Write-Fail "Google Chrome was not found on Windows. Install Chrome or add chrome.exe to PATH."
  }
  Write-Output "Chrome found: $chrome"
  exit 0
}

if ($Action -eq "status") {
  $skillProcesses = @(Get-SkillProcesses)
  $cdp = Test-Cdp
  Write-Output "profile=$ProfilePath"
  Write-Output "port=$Port"
  Write-Output "skill_processes=$($skillProcesses.Count)"
  Write-Output "cdp_healthy=$cdp"
  foreach ($process in $skillProcesses) {
    Write-Output "pid=$($process.ProcessId)"
  }
  exit 0
}

if ($Action -eq "stop") {
  $count = Stop-SkillChrome
  Write-Output "Stopped $count skill-owned Chrome process(es)."
  exit 0
}

Assert-PortOwnership

if (Test-Cdp) {
  Write-Output "Chrome CDP is already healthy at http://127.0.0.1:$Port/json/version"
  exit 0
}

$profileProcesses = @(Get-ProfileProcesses)
if ($profileProcesses.Count -gt 0) {
  Write-Output "Stopping stale skill-owned Chrome profile before restart..."
  Stop-SkillChrome | Out-Null
}

Start-SkillChrome
Assert-PortOwnership
Write-Output "Chrome CDP is healthy at http://127.0.0.1:$Port/json/version"
`;

const result = powershellEncoded(script, { stdio: 'inherit' });
exitFromResult(result, 'Windows Chrome debug helper failed');
