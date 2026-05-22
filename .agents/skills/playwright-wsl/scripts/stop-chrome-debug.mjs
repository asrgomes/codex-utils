#!/usr/bin/env node
import { cdpPort, runNodeScriptOrExit } from './lib.mjs';

runNodeScriptOrExit('doctor.mjs', ['--chrome-only'], { stdio: 'ignore' });
runNodeScriptOrExit('chrome-debug.mjs', ['stop', '--port', String(cdpPort)], {
  stdio: 'inherit',
});
