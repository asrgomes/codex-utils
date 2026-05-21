import assert from 'node:assert/strict';
import test from 'node:test';
import {
  createLazyBrowserContextGetter,
  createWindowsChromeMcpServer,
} from './playwright-mcp-wrapper.mjs';

function fakeContext() {
  return { id: 'context' };
}

function fakeBrowser(context = fakeContext()) {
  return {
    contexts() {
      return [context];
    },
  };
}

test('creating the MCP server does not run browser startup', async () => {
  const calls = [];
  const contextGetter = createLazyBrowserContextGetter({
    cdpEndpointValue: 'http://localhost:9223',
    cdpPortValue: 9223,
    connectOverCdp: async () => fakeBrowser(),
    ensureCdpHealth: async () => calls.push('health'),
    runSetup: (scriptName, args) => calls.push(['setup', scriptName, args]),
  });

  const server = await createWindowsChromeMcpServer({
    contextGetter,
    createConnection: async (config, getter) => {
      assert.equal(config.browser.browserName, 'chromium');
      assert.equal(getter, contextGetter);
      return { name: 'server' };
    },
  });

  assert.deepEqual(server, { name: 'server' });
  assert.deepEqual(calls, []);
});

test('first browser context request runs readiness checks and connects over CDP', async () => {
  const calls = [];
  const context = fakeContext();
  const contextGetter = createLazyBrowserContextGetter({
    cdpEndpointValue: 'http://localhost:9223',
    cdpPortValue: 9223,
    connectOverCdp: async (endpoint, options) => {
      calls.push(['connect', endpoint, options]);
      return fakeBrowser(context);
    },
    ensureCdpHealth: async () => calls.push('health'),
    runSetup: (scriptName, args) => calls.push(['setup', scriptName, args]),
  });

  assert.equal(await contextGetter(), context);
  assert.deepEqual(calls, [
    ['setup', 'doctor.mjs', ['--preflight']],
    ['setup', 'chrome-debug.mjs', ['ensure', '--port', '9223']],
    'health',
    ['connect', 'http://localhost:9223', { timeout: 30000 }],
  ]);
});

test('concurrent first browser context requests share one startup', async () => {
  const calls = [];
  const context = fakeContext();
  let releaseConnection;
  const contextGetter = createLazyBrowserContextGetter({
    cdpEndpointValue: 'http://localhost:9223',
    cdpPortValue: 9223,
    connectOverCdp: async () => {
      calls.push('connect');
      await new Promise((resolve) => {
        releaseConnection = resolve;
      });
      return fakeBrowser(context);
    },
    ensureCdpHealth: async () => calls.push('health'),
    runSetup: (scriptName) => calls.push(scriptName),
  });

  const first = contextGetter();
  const second = contextGetter();
  await Promise.resolve();
  releaseConnection();

  assert.deepEqual(await Promise.all([first, second]), [context, context]);
  assert.deepEqual(calls, ['doctor.mjs', 'chrome-debug.mjs', 'health', 'connect']);
});

test('failed lazy startup resets state so a later call can retry', async () => {
  const calls = [];
  const context = fakeContext();
  let attempts = 0;
  const contextGetter = createLazyBrowserContextGetter({
    cdpEndpointValue: 'http://localhost:9223',
    cdpPortValue: 9223,
    connectOverCdp: async () => {
      attempts++;
      calls.push(['connect', attempts]);
      if (attempts === 1) {
        throw new Error('temporary CDP failure');
      }
      return fakeBrowser(context);
    },
    ensureCdpHealth: async () => calls.push('health'),
    runSetup: (scriptName) => calls.push(scriptName),
  });

  await assert.rejects(contextGetter(), /temporary CDP failure/);
  assert.equal(await contextGetter(), context);
  assert.deepEqual(calls, [
    'doctor.mjs',
    'chrome-debug.mjs',
    'health',
    ['connect', 1],
    'doctor.mjs',
    'chrome-debug.mjs',
    'health',
    ['connect', 2],
  ]);
});
