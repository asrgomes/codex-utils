import assert from 'node:assert/strict';
import { mkdtempSync, existsSync } from 'node:fs';
import { readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  defaultSessionName,
  passthroughCommands,
  reservedCommands,
  normalizePlaywrightCliCommand,
  resolveDefaultSessionName,
  runManagedPlaywrightCliCommand,
} from './playwright-cli.mjs';

test('default session name follows the renamed skill', () => {
  assert.equal(resolveDefaultSessionName({}), 'playwright-wsl');
  assert.equal(
    resolveDefaultSessionName({ PLAYWRIGHT_WSL_SESSION: 'custom-playwright-wsl' }),
    'custom-playwright-wsl',
  );
  assert.equal(resolveDefaultSessionName({ WSL_PLAYWRIGHT_SESSION: 'custom-wsl' }), 'custom-wsl');
  assert.equal(
    resolveDefaultSessionName({ WINDOWS_CHROME_PLAYWRIGHT_SESSION: 'custom-legacy' }),
    'custom-legacy',
  );
  assert.equal(defaultSessionName, resolveDefaultSessionName());
});

test('open maps to a session goto command', () => {
  assert.deepEqual(
    normalizePlaywrightCliCommand(['open', 'https://example.com']),
    ['goto', 'https://example.com'],
  );
  assert.deepEqual(
    normalizePlaywrightCliCommand(['open']),
    ['goto', 'about:blank'],
  );
});

test('raw attach is reserved, while explicit cleanup commands pass through', () => {
  assert.ok(reservedCommands.has('attach'));
  assert.ok(passthroughCommands.has('detach'));
  assert.deepEqual(normalizePlaywrightCliCommand(['detach']), ['detach']);
  assert.throws(
    () => normalizePlaywrightCliCommand(['attach', '--cdp=http://localhost:9223']),
    /managed by this runner/,
  );
});

function listResult(browsers) {
  return {
    status: 0,
    stdout: JSON.stringify({ browsers }),
  };
}

function tempCachePath() {
  return path.join(mkdtempSync(path.join(os.tmpdir(), 'playwright-wsl-test-')), 'health-cache.json');
}

async function writeFreshCache(cachePath, overrides = {}) {
  await writeFile(cachePath, JSON.stringify({
    version: 1,
    validatedAt: Date.now(),
    sessionName: 'windows-chrome-test',
    cdpPort: 9223,
    profilePath: '',
    runtimeDir: '/runtime',
    ...overrides,
  }));
}

test('runner attaches through playwright-cli once and leaves the session open', async () => {
  const calls = [];
  const cachePath = tempCachePath();
  const result = await runManagedPlaywrightCliCommand(['snapshot'], {
    cachePath,
    cdpEndpointValue: 'http://localhost:9223',
    chromeSetup: () => calls.push(['chrome', 'ensure']),
    runCli: (args, options) => {
      calls.push(['cli', args, options.stdio]);
      if (args.includes('list')) {
        return listResult([]);
      }
      return { status: 0 };
    },
    sessionName: 'windows-chrome-test',
    fastStartEnv: { PLAYWRIGHT_WSL_FAST_START: '0' },
  });

  assert.deepEqual(result, { status: 0 });
  assert.deepEqual(calls, [
    ['chrome', 'ensure'],
    ['cli', ['-s=windows-chrome-test', 'list', '--json'], 'pipe'],
    ['cli', ['-s=windows-chrome-test', 'attach', '--cdp=http://localhost:9223'], 'pipe'],
    ['cli', ['-s=windows-chrome-test', 'snapshot'], 'inherit'],
  ]);
});

test('runner reuses an existing attached playwright-cli session', async () => {
  const calls = [];
  const cachePath = tempCachePath();
  const result = await runManagedPlaywrightCliCommand(['snapshot'], {
    cachePath,
    cdpEndpointValue: 'http://localhost:9223',
    chromeSetup: () => calls.push(['chrome', 'ensure']),
    runCli: (args, options) => {
      calls.push(['cli', args, options.stdio]);
      if (args.includes('list')) {
        return listResult([{
          name: 'windows-chrome-test',
          status: 'open',
          attached: true,
          compatible: true,
        }]);
      }
      return { status: 0 };
    },
    sessionName: 'windows-chrome-test',
    fastStartEnv: { PLAYWRIGHT_WSL_FAST_START: '0' },
  });

  assert.deepEqual(result, { status: 0 });
  assert.deepEqual(calls, [
    ['chrome', 'ensure'],
    ['cli', ['-s=windows-chrome-test', 'list', '--json'], 'pipe'],
    ['cli', ['-s=windows-chrome-test', 'snapshot'], 'inherit'],
  ]);
});

test('runner forwards explicit cleanup commands without opening Chrome', async () => {
  const calls = [];
  const result = await runManagedPlaywrightCliCommand(['detach'], {
    chromeSetup: () => calls.push(['chrome', 'ensure']),
    runCli: (args, options) => {
      calls.push(['cli', args, options.stdio]);
      return { status: 0 };
    },
    sessionName: 'windows-chrome-test',
  });

  assert.deepEqual(result, { status: 0 });
  assert.deepEqual(calls, [
    ['cli', ['-s=windows-chrome-test', 'detach'], 'inherit'],
  ]);
});

test('runner fast-starts when a fresh cache has healthy cdp and attached session', async () => {
  const calls = [];
  const cachePath = tempCachePath();
  await writeFreshCache(cachePath);

  const result = await runManagedPlaywrightCliCommand(['snapshot'], {
    cachePath,
    cdpPortValue: 9223,
    chromeSetup: () => calls.push(['chrome', 'ensure']),
    getCdpHealth: async () => ({ ok: true }),
    runCli: (args, options) => {
      calls.push(['cli', args, options.stdio]);
      if (args.includes('list')) {
        return listResult([{
          name: 'windows-chrome-test',
          status: 'open',
          attached: true,
          compatible: true,
        }]);
      }
      return { status: 0 };
    },
    runtimeDirValue: '/runtime',
    sessionName: 'windows-chrome-test',
  });

  assert.deepEqual(result, { status: 0 });
  assert.deepEqual(calls, [
    ['cli', ['-s=windows-chrome-test', 'list', '--json'], 'pipe'],
    ['cli', ['-s=windows-chrome-test', 'snapshot'], 'inherit'],
  ]);
});

test('runner falls back to full setup when fast start is disabled', async () => {
  const calls = [];
  const cachePath = tempCachePath();
  await writeFreshCache(cachePath);

  const result = await runManagedPlaywrightCliCommand(['snapshot'], {
    cachePath,
    cdpPortValue: 9223,
    chromeSetup: () => calls.push(['chrome', 'ensure']),
    fastStartEnv: { PLAYWRIGHT_WSL_FAST_START: '0' },
    getCdpHealth: async () => {
      calls.push(['cdp', 'health']);
      return { ok: true };
    },
    runCli: (args, options) => {
      calls.push(['cli', args, options.stdio]);
      if (args.includes('list')) {
        return listResult([{
          name: 'windows-chrome-test',
          status: 'open',
          attached: true,
          compatible: true,
        }]);
      }
      return { status: 0 };
    },
    runtimeDirValue: '/runtime',
    sessionName: 'windows-chrome-test',
  });

  assert.deepEqual(result, { status: 0 });
  assert.deepEqual(calls, [
    ['chrome', 'ensure'],
    ['cli', ['-s=windows-chrome-test', 'list', '--json'], 'pipe'],
    ['cli', ['-s=windows-chrome-test', 'snapshot'], 'inherit'],
  ]);
});

test('runner falls back to full setup when warm cache is unusable', async () => {
  const cases = [
    {
      name: 'missing cache',
      write: async () => {},
    },
    {
      name: 'stale cache',
      write: (cachePath) => writeFreshCache(cachePath, { validatedAt: Date.now() - 61_000 }),
    },
    {
      name: 'mismatched session',
      write: (cachePath) => writeFreshCache(cachePath, { sessionName: 'other-session' }),
    },
    {
      name: 'unhealthy cdp',
      write: (cachePath) => writeFreshCache(cachePath),
      getCdpHealth: async () => ({ ok: false }),
    },
    {
      name: 'unattached session',
      write: (cachePath) => writeFreshCache(cachePath),
      browsers: [{
        name: 'windows-chrome-test',
        status: 'open',
        attached: false,
        compatible: true,
      }],
    },
  ];

  for (const testCase of cases) {
    const calls = [];
    const cachePath = tempCachePath();
    await testCase.write(cachePath);

    const result = await runManagedPlaywrightCliCommand(['snapshot'], {
      cachePath,
      cdpPortValue: 9223,
      chromeSetup: () => calls.push(['chrome', 'ensure']),
      getCdpHealth: testCase.getCdpHealth ?? (async () => ({ ok: true })),
      runCli: (args, options) => {
        calls.push(['cli', args, options.stdio]);
        if (args.includes('list')) {
          return listResult(testCase.browsers ?? [{
            name: 'windows-chrome-test',
            status: 'open',
            attached: true,
            compatible: true,
          }]);
        }
        return { status: 0 };
      },
      runtimeDirValue: '/runtime',
      sessionName: 'windows-chrome-test',
    });

    assert.deepEqual(result, { status: 0 }, testCase.name);
    assert.ok(
      calls.some((call) => call[0] === 'chrome' && call[1] === 'ensure'),
      testCase.name,
    );
  }
});

test('runner writes warm cache after successful full setup', async () => {
  const cachePath = tempCachePath();

  const result = await runManagedPlaywrightCliCommand(['snapshot'], {
    cachePath,
    cdpPortValue: 9224,
    chromeSetup: () => {},
    fastStartEnv: { PLAYWRIGHT_WSL_FAST_START: '0' },
    runCli: (args) => {
      if (args.includes('list')) {
        return listResult([{
          name: 'windows-chrome-test',
          status: 'open',
          attached: true,
          compatible: true,
        }]);
      }
      return { status: 0 };
    },
    runtimeDirValue: '/runtime',
    sessionName: 'windows-chrome-test',
  });

  assert.deepEqual(result, { status: 0 });
  const cache = JSON.parse(await readFile(cachePath, 'utf8'));
  assert.equal(cache.version, 1);
  assert.equal(cache.sessionName, 'windows-chrome-test');
  assert.equal(cache.cdpPort, 9224);
  assert.equal(cache.runtimeDir, '/runtime');
});

test('runner invalidates warm cache after a warm-path command failure', async () => {
  const cachePath = tempCachePath();
  await writeFreshCache(cachePath);

  const result = await runManagedPlaywrightCliCommand(['snapshot'], {
    cachePath,
    cdpPortValue: 9223,
    chromeSetup: () => assert.fail('warm failure should not run full setup'),
    getCdpHealth: async () => ({ ok: true }),
    runCli: (args) => {
      if (args.includes('list')) {
        return listResult([{
          name: 'windows-chrome-test',
          status: 'open',
          attached: true,
          compatible: true,
        }]);
      }
      return { status: 17 };
    },
    runtimeDirValue: '/runtime',
    sessionName: 'windows-chrome-test',
  });

  assert.deepEqual(result, { status: 17 });
  assert.equal(existsSync(cachePath), false);
});
