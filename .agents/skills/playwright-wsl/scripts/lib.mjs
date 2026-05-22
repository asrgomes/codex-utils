import { spawnSync } from 'node:child_process';
import { accessSync, constants as fsConstants, existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';

export const MINIMUM_NODE_MAJOR = 24;
export const DEFAULT_CDP_PORT = 9223;
export const DEFAULT_CDP_TIMEOUT_MS = 3000;

export const scriptDir = import.meta.dirname;
export const skillDir = path.resolve(scriptDir, '..');
export const cdpPort = readIntegerEnv('WINDOWS_CHROME_CDP_PORT', DEFAULT_CDP_PORT);
export const cdpEndpoint = `http://localhost:${cdpPort}`;
export const runtimeDir = process.env.WINDOWS_CHROME_PLAYWRIGHT_RUNTIME_DIR ||
  path.join(skillDir, '.runtime');
export const playwrightBin = path.join(runtimeDir, 'node_modules', '.bin', 'playwright');
export const playwrightCliPath = path.join(
  runtimeDir,
  'node_modules',
  'playwright-core',
  'lib',
  'tools',
  'cli-client',
  'cli.js',
);

export function fail(message, code = 1) {
  console.error(`ERROR: ${message}`);
  process.exit(code);
}

export function readIntegerEnv(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === '') {
    return fallback;
  }

  const value = Number.parseInt(raw, 10);
  if (!Number.isInteger(value)) {
    fail(`${name} must be an integer. Observed: ${raw}`);
  }

  return value;
}

export function requireModernNode() {
  const major = Number.parseInt(process.versions.node.split('.')[0], 10);
  if (!Number.isInteger(major) || major < MINIMUM_NODE_MAJOR) {
    fail(`Node.js ${MINIMUM_NODE_MAJOR}+ is required. Observed: ${process.version}`);
  }
}

requireModernNode();

export function run(command, args, options = {}) {
  return spawnSync(command, args, {
    encoding: 'utf8',
    ...options,
  });
}

export function resultText(result) {
  return [
    result.stdout,
    result.stderr,
    result.error?.message,
  ].filter(Boolean).join('\n').trim();
}

export function runOrExit(command, args, options = {}) {
  const result = run(command, args, { stdio: 'inherit', ...options });
  if (result.error) {
    fail(`${command} failed: ${result.error.message}`);
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
  return result;
}

export function runNodeScript(scriptName, args = [], options = {}) {
  return run(process.execPath, [path.join(scriptDir, scriptName), ...args], options);
}

export function runNodeScriptOrExit(scriptName, args = [], options = {}) {
  return runOrExit(process.execPath, [path.join(scriptDir, scriptName), ...args], options);
}

function isExecutableFile(filePath) {
  try {
    accessSync(filePath, fsConstants.X_OK);
    return true;
  } catch {
    return false;
  }
}

export function commandExists(command) {
  return (process.env.PATH || '')
    .split(path.delimiter)
    .filter(Boolean)
    .some((directory) => isExecutableFile(path.join(directory, command)));
}

export function requireCommand(command) {
  if (!commandExists(command)) {
    fail(`Missing required command: ${command}`);
  }
}

export function requireWsl2() {
  const releasePath = '/proc/sys/kernel/osrelease';
  if (!existsSync(releasePath)) {
    fail('This skill only supports agents running inside WSL2 on Windows 11.');
  }
  const release = readFileSync(releasePath, 'utf8').trim().toLowerCase();
  if (!release.includes('microsoft-standard-wsl2')) {
    fail(`This skill only supports WSL2. Observed kernel release: ${release}`);
  }
}

export function requireMirroredNetworking() {
  requireCommand('wslinfo');
  const result = run('wslinfo', ['--networking-mode'], { stdio: 'pipe' });
  if (result.error || result.status !== 0) {
    const detail = resultText(result);
    fail(`Could not query WSL networking mode. Required: wslinfo --networking-mode prints 'mirrored'. ${detail}`);
  }
  const mode = (result.stdout || '').replace(/\r/g, '').trim();
  if (mode !== 'mirrored') {
    fail(`WSL networking mode must be mirrored. Observed: ${mode || '<empty>'}`);
  }
}

export async function getCdpVersion(port = cdpPort, timeoutMs = DEFAULT_CDP_TIMEOUT_MS) {
  const url = `http://localhost:${port}/json/version`;
  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(timeoutMs),
    });
    const body = await response.text();
    return {
      ok: response.ok && /"Browser"\s*:\s*"Chrome\//.test(body),
      statusCode: response.status,
      body,
    };
  } catch (error) {
    return { ok: false, error };
  }
}

export function powershellEncoded(script, options = {}) {
  const encoded = Buffer.from(script, 'utf16le').toString('base64');
  return run('powershell.exe', [
    '-NoProfile',
    '-NonInteractive',
    '-ExecutionPolicy',
    'Bypass',
    '-EncodedCommand',
    encoded,
  ], options);
}

export function psQuote(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

export function forwardCapturedToStderr(result) {
  if (result.stdout) {
    process.stderr.write(result.stdout);
  }
  if (result.stderr) {
    process.stderr.write(result.stderr);
  }
}

export function exitFromResult(result, fallbackMessage) {
  if (result.error) {
    fail(`${fallbackMessage}: ${result.error.message}`);
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

export function parseCliArgs(config) {
  try {
    return parseArgs({
      allowPositionals: true,
      strict: true,
      ...config,
    });
  } catch (error) {
    fail(error.message, 2);
  }
}

export function parseInteger(value, label) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed)) {
    fail(`${label} must be an integer. Observed: ${value}`, 2);
  }
  return parsed;
}
