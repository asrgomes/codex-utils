#!/usr/bin/env node
import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import {
  fail,
  playwrightBin,
  playwrightCliPath,
  runOrExit,
  runtimeDir,
} from './lib.mjs';

if (existsSync(playwrightBin) && existsSync(playwrightCliPath)) {
  console.log(`Playwright CLI already installed: ${playwrightBin}`);
  process.exit(0);
}

console.log(`Installing Playwright CLI into ${runtimeDir} ...`);
await mkdir(runtimeDir, { recursive: true });

runOrExit('npm', ['install', '--prefix', runtimeDir, 'playwright@latest'], {
  stdio: 'inherit',
});

if (!existsSync(playwrightBin)) {
  fail(`Playwright installed but binary was not found at ${playwrightBin}`);
}

if (!existsSync(playwrightCliPath)) {
  fail(`Playwright installed but playwright-cli entrypoint was not found at ${playwrightCliPath}`);
}

console.log(`Playwright CLI installed: ${playwrightBin}`);
