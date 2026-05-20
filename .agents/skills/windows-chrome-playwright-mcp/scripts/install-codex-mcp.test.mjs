import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';

const scriptDir = import.meta.dirname;
const installer = path.join(scriptDir, 'install-codex-mcp.mjs');
const wrapper = path.join(scriptDir, 'playwright-mcp-wrapper.mjs');

function runInstaller(fakeCodexBody) {
  const tempDir = mkdtempSync(path.join(tmpdir(), 'windows-chrome-mcp-test-'));
  const callsPath = path.join(tempDir, 'calls.jsonl');
  const fakeCodex = path.join(tempDir, 'codex');

  writeFileSync(fakeCodex, `#!/usr/bin/env node
const { appendFileSync } = require('node:fs');
const args = process.argv.slice(2);
appendFileSync(${JSON.stringify(callsPath)}, JSON.stringify(args) + '\\n');
${fakeCodexBody}
`);
  chmodSync(fakeCodex, 0o700);

  const result = spawnSync(process.execPath, [installer], {
    cwd: scriptDir,
    encoding: 'utf8',
    env: {
      ...process.env,
      PATH: `${tempDir}${path.delimiter}${process.env.PATH}`,
    },
  });

  const calls = readFileSync(callsPath, 'utf8')
    .trim()
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line));
  rmSync(tempDir, { recursive: true, force: true });

  return { calls, result };
}

test('registers a missing windows-chrome MCP server', () => {
  const { calls, result } = runInstaller(`
if (args[0] === 'mcp' && args[1] === 'get') process.exit(1);
if (args[0] === 'mcp' && args[1] === 'add') process.exit(0);
process.exit(2);
`);

  assert.equal(result.status, 0, `${JSON.stringify(calls)}\n${result.stdout}\n${result.stderr}`);
  assert.deepEqual(calls, [
    ['mcp', 'get', 'windows-chrome'],
    ['mcp', 'add', 'windows-chrome', '--', process.execPath, wrapper],
  ]);
});

test('updates a stale windows-chrome MCP server', () => {
  const { calls, result } = runInstaller(`
if (args[0] === 'mcp' && args[1] === 'get') {
  console.log('windows-chrome');
  console.log('command = "/old/node"');
  console.log('args = ["/old/wrapper.mjs"]');
  process.exit(0);
}
if (args[0] === 'mcp' && args[1] === 'remove') process.exit(0);
if (args[0] === 'mcp' && args[1] === 'add') process.exit(0);
process.exit(2);
`);

  assert.equal(result.status, 0, `${JSON.stringify(calls)}\n${result.stdout}\n${result.stderr}`);
  assert.deepEqual(calls, [
    ['mcp', 'get', 'windows-chrome'],
    ['mcp', 'remove', 'windows-chrome'],
    ['mcp', 'add', 'windows-chrome', '--', process.execPath, wrapper],
  ]);
});

test('keeps an existing matching windows-chrome MCP server', () => {
  const { calls, result } = runInstaller(`
if (args[0] === 'mcp' && args[1] === 'get') {
  console.log('windows-chrome');
  console.log(${JSON.stringify(process.execPath)});
  console.log(${JSON.stringify(wrapper)});
  process.exit(0);
}
process.exit(2);
`);

  assert.equal(result.status, 0, `${JSON.stringify(calls)}\n${result.stdout}\n${result.stderr}`);
  assert.deepEqual(calls, [
    ['mcp', 'get', 'windows-chrome'],
  ]);
});
