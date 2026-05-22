#!/usr/bin/env node
import {
  cdpPort,
  getCdpVersion,
  runNodeScriptOrExit,
} from './lib.mjs';

runNodeScriptOrExit('doctor.mjs', ['--chrome-only'], { stdio: 'ignore' });
runNodeScriptOrExit('chrome-debug.mjs', ['status', '--port', String(cdpPort)], {
  stdio: 'inherit',
});

const result = await getCdpVersion(cdpPort, 3000);
console.log(`wsl_cdp_reachable=${result.ok ? 'true' : 'false'}`);
