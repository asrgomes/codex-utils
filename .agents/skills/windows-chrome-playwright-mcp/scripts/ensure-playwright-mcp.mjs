#!/usr/bin/env node
import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import {
  fail,
  mcpBin,
  runOrExit,
  runtimeDir,
} from './lib.mjs';

if (existsSync(mcpBin)) {
  console.log(`Playwright MCP already installed: ${mcpBin}`);
  process.exit(0);
}

console.log(`Installing @playwright/mcp into ${runtimeDir} ...`);
await mkdir(runtimeDir, { recursive: true });

runOrExit('npm', ['install', '--prefix', runtimeDir, '@playwright/mcp@latest'], {
  stdio: 'inherit',
});

if (!existsSync(mcpBin)) {
  fail(`@playwright/mcp installed but binary was not found at ${mcpBin}`);
}

console.log(`Playwright MCP installed: ${mcpBin}`);
