#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import {
  cdpEndpoint,
  cdpPort,
  exitFromResult,
  fail,
  forwardCapturedToStderr,
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

runSetup('doctor.mjs', ['--preflight']);
runSetup('ensure-playwright-mcp.mjs');
runSetup('ensure-windows-chrome-debug.mjs');
runSetup('doctor.mjs', ['--cdp']);

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
