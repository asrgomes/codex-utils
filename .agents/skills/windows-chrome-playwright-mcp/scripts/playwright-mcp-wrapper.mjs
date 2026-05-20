#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import {
  cdpEndpoint,
  cdpPort,
  exitFromResult,
  fail,
  forwardCapturedToStderr,
  getCdpVersion,
  mcpBin,
  runNodeScript,
} from './lib.mjs';

function runSetup(scriptName, args = []) {
  const result = runNodeScript(scriptName, args, {
    encoding: 'utf8',
    stdio: 'pipe',
  });
  forwardCapturedToStderr(result);
  exitFromResult(result, `${scriptName} failed`);
}

async function requireCdpHealth() {
  const result = await getCdpVersion(cdpPort, 3000);
  if (!result.ok) {
    const detail = result.error?.message || `HTTP status ${result.statusCode ?? '<none>'}`;
    fail(`Chrome CDP is not reachable from WSL at ${cdpEndpoint}/json/version: ${detail}`);
  }
}

runSetup('doctor.mjs', ['--preflight']);
runSetup('ensure-playwright-mcp.mjs');
runSetup('chrome-debug.mjs', ['ensure', '--port', String(cdpPort)]);
await requireCdpHealth();

const result = spawnSync(mcpBin, [
  '--cdp-endpoint',
  cdpEndpoint,
  '--cdp-timeout',
  '30000',
], {
  stdio: 'inherit',
});

if (result.error) {
  fail(`Failed to start Playwright MCP for Chrome CDP port ${cdpPort}: ${result.error.message}`);
}
process.exit(result.status ?? 0);
