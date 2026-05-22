#!/usr/bin/env node
import {
  cdpPort,
  exitFromResult,
  fail,
  getCdpVersion,
  parseCliArgs,
  requireCommand,
  requireMirroredNetworking,
  requireWsl2,
  resultText,
  runNodeScript,
} from './lib.mjs';

const { positionals, values } = parseCliArgs({
  options: {
    preflight: { type: 'boolean' },
    cdp: { type: 'boolean' },
    'chrome-only': { type: 'boolean' },
  },
});

const selectedModes = [
  values.preflight && '--preflight',
  values.cdp && '--cdp',
  values['chrome-only'] && '--chrome-only',
  positionals[0],
].filter(Boolean);

if (selectedModes.length > 1) {
  fail(`Choose one doctor mode, not: ${selectedModes.join(', ')}`);
}

const mode = selectedModes[0] || 'full';

function requireWindowsChrome() {
  const result = runNodeScript('chrome-debug.mjs', ['check-chrome', '--port', String(cdpPort)], {
    encoding: 'utf8',
    stdio: 'pipe',
  });
  if (result.error || result.status !== 0) {
    const detail = resultText(result);
    fail(detail || 'Google Chrome was not found on Windows.');
  }
}

function ensurePlaywrightCliInstalled() {
  const result = runNodeScript('ensure-playwright-cli.mjs', [], {
    stdio: 'inherit',
  });
  exitFromResult(result, 'Playwright CLI installation failed');
}

async function requireCdpHealth() {
  const url = `http://localhost:${cdpPort}/json/version`;
  const result = await getCdpVersion(cdpPort, 3000);
  if (!result.ok) {
    const detail = result.error?.message || `HTTP status ${result.statusCode ?? '<none>'}`;
    fail(`Chrome CDP is not reachable from WSL at ${url}: ${detail}`);
  }
}

requireWsl2();
requireMirroredNetworking();
requireCommand('powershell.exe');
requireWindowsChrome();

if (mode !== '--chrome-only') {
  ensurePlaywrightCliInstalled();
}

if (mode === '--cdp' || mode === 'full') {
  await requireCdpHealth();
} else if (mode !== '--preflight' && mode !== '--chrome-only') {
  fail(`Unknown doctor mode: ${mode}`);
}

console.log(`Doctor checks passed (${mode}).`);
