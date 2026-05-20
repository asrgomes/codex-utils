#!/usr/bin/env node
import { runNodeScriptOrExit } from './lib.mjs';

runNodeScriptOrExit('doctor.mjs', ['--preflight'], { stdio: 'inherit' });
runNodeScriptOrExit('ensure-playwright-mcp.mjs', [], { stdio: 'inherit' });
runNodeScriptOrExit('install-codex-mcp.mjs', [], { stdio: 'inherit' });

console.log(`Bootstrap complete.

If Codex does not expose the new windows-chrome MCP tools in this session,
restart the Codex CLI session and try the browser task again.`);
