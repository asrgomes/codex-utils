#!/usr/bin/env node
import { runNodeScriptOrExit } from './lib.mjs';

runNodeScriptOrExit('doctor.mjs', ['--preflight'], { stdio: 'inherit' });

console.log(`Bootstrap complete.

Run browser actions with:

  node scripts/playwright-cli.mjs <playwright-cli command>`);
