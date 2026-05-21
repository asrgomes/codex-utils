#!/usr/bin/env node
import { createRequire } from 'node:module';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import {
  cdpEndpoint,
  cdpPort,
  exitFromResult,
  fail,
  forwardCapturedToStderr,
  getCdpVersion,
  runNodeScript,
  runtimeDir,
} from './lib.mjs';

const runtimeRequire = createRequire(path.join(runtimeDir, 'package.json'));

export function runSetup(scriptName, args = []) {
  const result = runNodeScript(scriptName, args, {
    encoding: 'utf8',
    stdio: 'pipe',
  });
  forwardCapturedToStderr(result);
  exitFromResult(result, `${scriptName} failed`);
}

export async function requireCdpHealth({
  cdpEndpointValue = cdpEndpoint,
  cdpPortValue = cdpPort,
} = {}) {
  const result = await getCdpVersion(cdpPortValue, 3000);
  if (!result.ok) {
    const detail = result.error?.message || `HTTP status ${result.statusCode ?? '<none>'}`;
    fail(`Chrome CDP is not reachable from WSL at ${cdpEndpointValue}/json/version: ${detail}`);
  }
}

export function loadRuntimeModules(requireFn = runtimeRequire) {
  try {
    const { createConnection } = requireFn('@playwright/mcp');
    const { chromium } = requireFn('playwright');
    const { StdioServerTransport } = requireFn('playwright-core/lib/utilsBundle');
    return { chromium, createConnection, StdioServerTransport };
  } catch (error) {
    fail(
      `Playwright MCP runtime is not installed under ${runtimeDir}. ` +
      `Run node scripts/bootstrap.mjs before using the windows-chrome MCP server. ${error.message}`,
    );
  }
}

function requireBrowserContext(browser) {
  const contexts = browser.contexts();
  if (contexts.length === 0) {
    fail('Connected to Chrome CDP, but no browser context is available.');
  }
  return contexts[0];
}

export function createLazyBrowserContextGetter({
  cdpEndpointValue = cdpEndpoint,
  cdpPortValue = cdpPort,
  connectOverCdp,
  ensureCdpHealth: ensureHealth = requireCdpHealth,
  runSetup: setup = runSetup,
} = {}) {
  let contextPromise;

  async function initializeContext() {
    setup('doctor.mjs', ['--preflight']);
    setup('chrome-debug.mjs', ['ensure', '--port', String(cdpPortValue)]);
    await ensureHealth({ cdpEndpointValue, cdpPortValue });
    const browser = await connectOverCdp(cdpEndpointValue, { timeout: 30000 });
    return requireBrowserContext(browser);
  }

  return () => {
    if (!contextPromise) {
      contextPromise = initializeContext().catch((error) => {
        contextPromise = undefined;
        throw error;
      });
    }
    return contextPromise;
  };
}

export async function createWindowsChromeMcpServer({
  contextGetter,
  createConnection,
} = {}) {
  const modules = (!createConnection || !contextGetter) ? loadRuntimeModules() : {};
  const connectionFactory = createConnection ?? modules.createConnection;
  const lazyContextGetter = contextGetter ?? createLazyBrowserContextGetter({
    connectOverCdp: modules.chromium.connectOverCDP.bind(modules.chromium),
  });

  return await connectionFactory({
    browser: {
      browserName: 'chromium',
    },
  }, lazyContextGetter);
}

export async function main() {
  const { StdioServerTransport } = loadRuntimeModules();
  const server = await createWindowsChromeMcpServer();
  const transport = new StdioServerTransport();
  process.stdin.on('end', () => void transport.close());
  await server.connect(transport);
}

const isMain = process.argv[1] &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (isMain) {
  await main().catch((error) => {
    fail(`Failed to start lazy Windows Chrome Playwright MCP server: ${error.message}`);
  });
}
