#!/usr/bin/env node
import { mkdir, readFile, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import {
  cdpEndpoint,
  cdpPort,
  exitFromResult,
  fail,
  forwardCapturedToStderr,
  getCdpVersion,
  playwrightCliPath,
  run,
  runNodeScript,
  runtimeDir,
} from './lib.mjs';

export const warmCacheVersion = 1;
export const warmCacheTtlMs = 60_000;
export const defaultWarmCachePath = path.join(runtimeDir, 'health-cache.json');

export function resolveDefaultSessionName(env = process.env) {
  return env.PLAYWRIGHT_WSL_SESSION ||
    env.WSL_PLAYWRIGHT_SESSION ||
    env.WINDOWS_CHROME_PLAYWRIGHT_SESSION ||
    'playwright-wsl';
}

export const defaultSessionName = resolveDefaultSessionName();

export const reservedCommands = new Set([
  'attach',
]);

export const passthroughCommands = new Set([
  'close',
  'close-all',
  'delete-data',
  'detach',
  'install',
  'install-browser',
  'kill-all',
  'list',
  'show',
]);

export function normalizePlaywrightCliCommand(args) {
  const [command, ...rest] = args;
  if (!command) {
    return ['snapshot'];
  }

  if (command === 'open') {
    return ['goto', rest[0] || 'about:blank'];
  }

  if (reservedCommands.has(command)) {
    throw new Error(
      `playwright-cli lifecycle command '${command}' is managed by this runner.`,
    );
  }

  return args;
}

export function runPlaywrightCli(args, options = {}) {
  return run(process.execPath, [playwrightCliPath, ...args], options);
}

export function runChromeSetup() {
  const doctor = runNodeScript('doctor.mjs', ['--preflight'], { stdio: 'inherit' });
  exitFromResult(doctor, 'Playwright WSL preflight failed');

  const chrome = runNodeScript('chrome-debug.mjs', ['ensure', '--port', String(cdpPort)], {
    stdio: 'inherit',
  });
  exitFromResult(chrome, 'Windows Chrome startup failed');
}

function isSuccess(result) {
  return !result.error && result.status === 0;
}

function parseListResult(result) {
  try {
    return JSON.parse(result.stdout || '{}');
  } catch (error) {
    throw new Error(`Could not parse playwright-cli list output: ${error.message}`);
  }
}

export function hasAttachedSession(listResult, sessionName) {
  const payload = parseListResult(listResult);
  return (payload.browsers || []).some((browser) =>
    browser.name === sessionName &&
    browser.status === 'open' &&
    browser.attached === true &&
    browser.compatible !== false
  );
}

function fastStartEnabled(env) {
  return env.PLAYWRIGHT_WSL_FAST_START !== '0';
}

async function readWarmCache(cachePath) {
  try {
    return JSON.parse(await readFile(cachePath, 'utf8'));
  } catch {
    return null;
  }
}

function matchesWarmCache(cache, {
  cdpPortValue,
  now,
  profilePath,
  runtimeDirValue,
  sessionName,
  ttlMs,
}) {
  return cache?.version === warmCacheVersion &&
    cache.sessionName === sessionName &&
    cache.cdpPort === cdpPortValue &&
    cache.profilePath === profilePath &&
    cache.runtimeDir === runtimeDirValue &&
    Number.isFinite(cache.validatedAt) &&
    now - cache.validatedAt >= 0 &&
    now - cache.validatedAt <= ttlMs;
}

async function writeWarmCache(cachePath, {
  cdpPortValue,
  now,
  profilePath,
  runtimeDirValue,
  sessionName,
}) {
  await mkdir(path.dirname(cachePath), { recursive: true });
  await writeFile(cachePath, JSON.stringify({
    version: warmCacheVersion,
    validatedAt: now,
    sessionName,
    cdpPort: cdpPortValue,
    profilePath,
    runtimeDir: runtimeDirValue,
  }, null, 2));
}

async function invalidateWarmCache(cachePath) {
  try {
    await unlink(cachePath);
  } catch {
    // Missing or unreadable caches should not mask the browser command result.
  }
}

async function canUseWarmStart({
  cachePath,
  cdpPortValue,
  getCdpHealth,
  now,
  profilePath,
  runCli,
  runtimeDirValue,
  session,
  sessionName,
  ttlMs,
}) {
  const cache = await readWarmCache(cachePath);
  if (!matchesWarmCache(cache, {
    cdpPortValue,
    now,
    profilePath,
    runtimeDirValue,
    sessionName,
    ttlMs,
  })) {
    return false;
  }

  const health = await getCdpHealth(cdpPortValue, 750);
  if (!health.ok) {
    return false;
  }

  const list = runCli([session, 'list', '--json'], { stdio: 'pipe' });
  if (!isSuccess(list)) {
    return false;
  }

  try {
    return hasAttachedSession(list, sessionName);
  } catch {
    return false;
  }
}

export function ensurePlaywrightCliSession({
  cdpEndpointValue,
  runCli,
  session,
  sessionName,
}) {
  const list = runCli([session, 'list', '--json'], { stdio: 'pipe' });
  if (!isSuccess(list)) {
    forwardCapturedToStderr(list);
    return list;
  }

  if (hasAttachedSession(list, sessionName)) {
    return { status: 0 };
  }

  const attach = runCli([session, 'attach', `--cdp=${cdpEndpointValue}`], { stdio: 'pipe' });
  if (!isSuccess(attach)) {
    forwardCapturedToStderr(attach);
  }
  return attach;
}

export async function runManagedPlaywrightCliCommand(args, {
  cachePath = defaultWarmCachePath,
  cdpEndpointValue = cdpEndpoint,
  cdpPortValue = cdpPort,
  chromeSetup = runChromeSetup,
  fastStartEnv = process.env,
  getCdpHealth = getCdpVersion,
  now = Date.now(),
  profilePath = process.env.WINDOWS_CHROME_PROFILE_PATH ?? '',
  runCli = runPlaywrightCli,
  runtimeDirValue = runtimeDir,
  sessionName = defaultSessionName,
  ttlMs = warmCacheTtlMs,
} = {}) {
  const command = normalizePlaywrightCliCommand(args);
  const session = `-s=${sessionName}`;

  if (passthroughCommands.has(command[0])) {
    return runCli([session, ...command], { stdio: 'inherit' });
  }

  if (fastStartEnabled(fastStartEnv) && await canUseWarmStart({
    cachePath,
    cdpPortValue,
    getCdpHealth,
    now,
    profilePath,
    runCli,
    runtimeDirValue,
    session,
    sessionName,
    ttlMs,
  })) {
    const result = runCli([session, ...command], { stdio: 'inherit' });
    if (!isSuccess(result)) {
      await invalidateWarmCache(cachePath);
    }
    return result;
  }

  chromeSetup();
  const attach = ensurePlaywrightCliSession({
    cdpEndpointValue,
    runCli,
    session,
    sessionName,
  });
  if (!isSuccess(attach)) {
    return attach;
  }

  const result = runCli([session, ...command], { stdio: 'inherit' });
  if (isSuccess(result)) {
    try {
      await writeWarmCache(cachePath, {
        cdpPortValue,
        now: Date.now(),
        profilePath,
        runtimeDirValue,
        sessionName,
      });
    } catch {
      // Fast-start caching is an optimization; command success should not depend on it.
    }
  }
  return result;
}

export async function main(args = process.argv.slice(2)) {
  try {
    const result = await runManagedPlaywrightCliCommand(args);
    exitFromResult(result, 'playwright-cli command failed');
  } catch (error) {
    fail(error.message, 2);
  }
}

const isMain = process.argv[1] &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (isMain) {
  await main();
}
