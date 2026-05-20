#!/usr/bin/env node
import path from 'node:path';
import {
  fail,
  requireCommand,
  resultText,
  run,
  runOrExit,
  scriptDir,
} from './lib.mjs';

const serverName = process.env.WINDOWS_CHROME_MCP_NAME || 'windows-chrome';
const wrapper = path.join(scriptDir, 'playwright-mcp-wrapper.mjs');

requireCommand('codex');

function serverMatches(output) {
  const text = output.replace(/\r/g, '');
  return text.includes(process.execPath) &&
    text.includes(wrapper) &&
    !text.toLowerCase().includes('(disabled)');
}

function addServer() {
  runOrExit('codex', ['mcp', 'add', serverName, '--', process.execPath, wrapper], {
    stdio: 'inherit',
  });
  console.log(`Registered Codex MCP server '${serverName}' -> ${process.execPath} ${wrapper}`);
}

const getResult = run('codex', ['mcp', 'get', serverName], {
  stdio: 'pipe',
});

if (getResult.status === 0) {
  const current = resultText(getResult);
  if (serverMatches(current)) {
    console.log(`Codex MCP server '${serverName}' is already registered correctly.`);
    process.exit(0);
  }

  console.log(`Replacing stale Codex MCP server '${serverName}'.`);
  runOrExit('codex', ['mcp', 'remove', serverName], {
    stdio: 'inherit',
  });
  addServer();
  process.exit(0);
}

if (getResult.error) {
  fail(`Could not query Codex MCP server '${serverName}': ${getResult.error.message}`);
}

addServer();
