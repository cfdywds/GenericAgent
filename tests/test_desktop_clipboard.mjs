import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const appJsPath = path.resolve('frontends/desktop/static/app.js');
const appJs = fs.readFileSync(appJsPath, 'utf8');

function extractFunctionSource(source, name) {
  const marker = `function ${name}`;
  const asyncMarker = `async ${marker}`;
  let start = source.indexOf(asyncMarker);
  if (start < 0) start = source.indexOf(marker);
  if (start < 0) return '';
  const signatureEnd = source.indexOf(')', start);
  const bodyStart = source.indexOf('{', signatureEnd);
  if (bodyStart < 0) throw new Error(`missing body for ${name}`);
  let depth = 0;
  for (let i = bodyStart; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === '{') depth += 1;
    if (ch === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`unterminated function ${name}`);
}

function loadClipboardHarness(extra = {}) {
  const sandbox = {
    console: { warn: (...args) => sandbox.warns.push(args) },
    warns: [],
    ...extra,
  };
  vm.createContext(sandbox);
  const source = [
    extractFunctionSource(appJs, 'clipboardErrorDetail'),
    extractFunctionSource(appJs, 'copyViaExecCommand'),
    extractFunctionSource(appJs, 'writeClipboardText'),
  ].join('\n');
  vm.runInContext(source, sandbox, { filename: appJsPath });
  return sandbox;
}

test('writeClipboardText uses Tauri native clipboard first in desktop shell', async () => {
  const calls = [];
  const sandbox = loadClipboardHarness({
    window: {
      __TAURI__: { core: { invoke: async () => { throw new Error('should use ga wrapper'); } } },
      ga: {
        tauriInvoke: async (name, args) => { calls.push({ name, args }); },
      },
    },
    navigator: { clipboard: { writeText: async () => { throw new Error('browser clipboard should not be used'); } } },
  });

  const ok = await sandbox.writeClipboardText('hello');

  assert.equal(ok, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].name, 'copy_text');
  assert.equal(calls[0].args.text, 'hello');
});

test('writeClipboardText falls back to execCommand outside Tauri', async () => {
  const calls = [];
  const sandbox = loadClipboardHarness({
    window: {},
    navigator: {},
    document: {
      body: { appendChild: (el) => calls.push(['append', el.value]) },
      createElement: () => ({
        style: {},
        setAttribute: () => {},
        focus: () => calls.push(['focus']),
        select: () => calls.push(['select']),
        remove: () => calls.push(['remove']),
      }),
      execCommand: (cmd) => { calls.push(['exec', cmd]); return true; },
      getSelection: () => ({ rangeCount: 0, removeAllRanges: () => {}, addRange: () => {} }),
    },
  });

  const ok = await sandbox.writeClipboardText('browser copy');

  assert.equal(ok, true);
  assert.deepEqual(calls.map(c => c[0]), ['append', 'focus', 'select', 'exec', 'remove']);
  assert.equal(calls[0][1], 'browser copy');
});

test('writeClipboardText uses Clipboard API when execCommand fails', async () => {
  let copied = '';
  const sandbox = loadClipboardHarness({
    window: {},
    navigator: { clipboard: { writeText: async (text) => { copied = text; } } },
    document: {
      body: { appendChild: () => {} },
      createElement: () => ({ style: {}, setAttribute: () => {}, focus: () => {}, select: () => {}, remove: () => {} }),
      execCommand: () => false,
      getSelection: () => ({ rangeCount: 0, removeAllRanges: () => {}, addRange: () => {} }),
    },
  });

  const ok = await sandbox.writeClipboardText('browser clipboard');

  assert.equal(ok, true);
  assert.equal(copied, 'browser clipboard');
});

test('writeClipboardText reports failure when no clipboard path works', async () => {
  const toasts = [];
  const sandbox = loadClipboardHarness({
    window: {},
    navigator: { clipboard: { writeText: async () => { throw new Error('denied'); } } },
    document: { body: null, execCommand: () => false },
    t: (key) => ({ 'err.copy': 'Copy failed' }[key] || key),
    showChanToast: (title, detail, kind) => toasts.push({ title, detail, kind }),
  });

  const ok = await sandbox.writeClipboardText('nope');

  assert.equal(ok, false);
  assert.deepEqual(toasts, [{ title: 'Copy failed', detail: 'denied', kind: 'err' }]);
  assert.equal(sandbox.warns.length, 1);
});