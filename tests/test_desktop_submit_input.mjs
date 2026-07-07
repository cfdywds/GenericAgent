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
  const bodyStart = source.indexOf('{', start);
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

function loadSubmitHarness({ text, cancelOk = true }) {
  const events = { systems: [], errors: [], sends: [], focusCount: 0 };
  const inputEl = {
    innerHTML: text,
    focus() { events.focusCount++; },
  };
  const sandbox = {
    inputEl,
    composerText: () => text,
    sendPrompt: async (prompt) => {
      events.sends.push(prompt);
      return true;
    },
    setComposerLocked: () => {},
    syncAskUserUi: () => {},
    showToast: () => {},
    showError: (msg) => events.errors.push(String(msg)),
    showSystem: (msg) => events.systems.push(String(msg)),
    t: (key) => ({
      'slash.help': 'Commands',
      'slash.unknown': 'Unknown command',
      'sys.stopRequested': 'Stop requested',
    }[key] || key),
    newSession: async () => { events.newSession = true; },
    activeSess: () => ({ messages: [] }),
    renderAllMessages: () => { events.rendered = true; },
    cancelPrompt: async () => cancelOk,
    openSettings: () => { events.settings = true; },
  };
  vm.createContext(sandbox);
  const source = [
    'var _submitInFlight = false;',
    extractFunctionSource(appJs, 'handleSlash'),
    extractFunctionSource(appJs, 'submitInput'),
  ].join('\n');
  vm.runInContext(source, sandbox, { filename: appJsPath });
  return { events, inputEl, submitInput: sandbox.submitInput };
}

test('unknown slash command preserves composer text', async () => {
  const text = '/copper 铜';
  const { events, inputEl, submitInput } = loadSubmitHarness({ text });

  await submitInput();

  assert.equal(inputEl.innerHTML, text);
  assert.equal(events.focusCount, 1);
  assert.deepEqual(events.systems, ['Unknown command: /copper']);
  assert.deepEqual(events.sends, []);
});

test('failed slash command preserves composer text', async () => {
  const text = '/stop 铜';
  const { events, inputEl, submitInput } = loadSubmitHarness({ text, cancelOk: false });

  await submitInput();

  assert.equal(inputEl.innerHTML, text);
  assert.equal(events.focusCount, 1);
  assert.deepEqual(events.systems, []);
});

test('successful slash command clears composer text', async () => {
  const text = '/help';
  const { events, inputEl, submitInput } = loadSubmitHarness({ text });

  await submitInput();

  assert.equal(inputEl.innerHTML, '');
  assert.equal(events.focusCount, 0);
  assert.deepEqual(events.systems, ['Commands']);
});
test('chat composer uses the unified send binding without legacy duplicate listeners', () => {
  assert.equal(appJs.includes("sendBtn.addEventListener('click'"), false);
  assert.equal(appJs.includes("inputEl.addEventListener('keydown'"), false);
  assert.match(appJs, /function doSend\(meta = \{\}\) \{ opts\.onSend\?\.\(meta\); \}/);
  assert.match(appJs, /doSend\(\{ source: 'keyboard', event: e \}\);/);
  assert.match(appJs, /doSend\(\{ source: 'button', event: e \}\);/);
  assert.match(appJs, /if \(meta\.source === 'button' && sess && rt\(sess\)\.busy\) \{ cancelPrompt\(\); return; \}/);
});
