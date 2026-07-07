import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const appJsPath = path.resolve('frontends/desktop/static/app.js');
const appJs = fs.readFileSync(appJsPath, 'utf8');

function extractFunctionSource(source, name) {
  const marker = `function ${name}`;
  let start = source.indexOf(marker);
  if (start < 0) return '';
  if (source.slice(start - 6, start) === 'async ') start -= 6;
  const signatureEnd = source.indexOf(')', start);
  const bodyStart = source.indexOf('{', signatureEnd);
  if (bodyStart < 0) throw new Error(`missing body for ${name}`);
  let depth = 0;
  for (let i = bodyStart; i < source.length; i++) {
    const ch = source[i];
    if (ch === '{') depth++;
    if (ch === '}') {
      depth--;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`unterminated function ${name}`);
}

function loadHarness(fetchImpl, bridgeToken = 'test-token') {
  const sandbox = {
    window: { ga: { bridgeToken } },
    bridgeHost: () => 'http://bridge.test',
    fetch: fetchImpl,
  };
  vm.createContext(sandbox);
  const source = [
    extractFunctionSource(appJs, 'bridgeFetch'),
    extractFunctionSource(appJs, 'uploadOne'),
  ].join('\n');
  vm.runInContext(source, sandbox, { filename: appJsPath });
  return sandbox;
}

test('uploadOne sends bridge token and JSON body', async () => {
  let captured = null;
  const sandbox = loadHarness(async (url, init) => {
    captured = { url, init };
    return {
      ok: true,
      text: async () => JSON.stringify({ ok: true, path: 'D:/tmp/pasted.png' }),
    };
  });

  const pathOut = await sandbox.uploadOne('铜.png', 'data:image/png;base64,AA==', 'sess-1');

  assert.equal(pathOut, 'D:/tmp/pasted.png');
  assert.equal(captured.url, 'http://bridge.test/upload');
  assert.equal(captured.init.method, 'POST');
  assert.equal(captured.init.headers['X-GA-Bridge-Token'], 'test-token');
  assert.equal(captured.init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(captured.init.body), {
    name: '铜.png',
    dataUrl: 'data:image/png;base64,AA==',
    sid: 'sess-1',
  });
});

test('bridgeFetch reports plain text bridge errors without JSON parse noise', async () => {
  const sandbox = loadHarness(async () => ({
    ok: false,
    statusText: 'Forbidden',
    text: async () => 'Bridge token required',
  }));

  await assert.rejects(
    () => sandbox.bridgeFetch('/upload', { method: 'POST', body: { name: 'x' } }),
    (err) => {
      assert.equal(err.message, 'Bridge token required');
      assert.doesNotMatch(err.message, /Unexpected token/);
      return true;
    },
  );
});
