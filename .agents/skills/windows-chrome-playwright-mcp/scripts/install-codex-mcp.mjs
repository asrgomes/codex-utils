#!/usr/bin/env node
import path from 'node:path';
import {
  requireCommand,
  run,
  runOrExit,
  scriptDir,
} from './lib.mjs';

const serverName = process.env.WINDOWS_CHROME_MCP_NAME || 'windows-chrome';
const wrapper = path.join(scriptDir, 'playwright-mcp-wrapper.mjs');

requireCommand('codex');

const getResult = run('codex', ['mcp', 'get', serverName], {
  stdio: 'ignore',
});
if (getResult.status === 0) {
  console.log(`Codex MCP server '${serverName}' already exists.`);
  console.log('');
  console.log('If it points at an older command, update it manually:');
  console.log(`  codex mcp remove ${serverName}`);
  console.log(`  codex mcp add ${serverName} -- ${process.execPath} ${wrapper}`);
  process.exit(0);
}

runOrExit('codex', ['mcp', 'add', serverName, '--', process.execPath, wrapper], {
  stdio: 'inherit',
});
console.log(`Registered Codex MCP server '${serverName}' -> ${process.execPath} ${wrapper}`);
