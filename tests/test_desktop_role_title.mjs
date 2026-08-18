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

function loadTitleHarness() {
  const sandbox = {
    assistantStructuredText: (message) => message.content || '',
    stripAttachPlaceholders: (text) => String(text || ''),
    t: (key) => key === 'conv.defaultTitle' ? 'New chat' : key,
  };
  vm.createContext(sandbox);
  vm.runInContext([
    extractFunctionSource(appJs, 'isAutoTitle'),
    extractFunctionSource(appJs, 'roleAwareTitle'),
    extractFunctionSource(appJs, 'displayTitle'),
  ].join('\n'), sandbox, { filename: appJsPath });
  return sandbox;
}

function loadRoleSyncHarness() {
  let renderCount = 0;
  const sandbox = {
    currentPage: 'chat',
    renderRoleManager: () => {},
    renderSessionList: () => { renderCount++; },
  };
  vm.createContext(sandbox);
  vm.runInContext(extractFunctionSource(appJs, 'syncSessionRole'), sandbox, { filename: appJsPath });
  return { sandbox, renderCount: () => renderCount };
}

function loadRoleSelectionHarness() {
  let renderCount = 0;
  let request = null;
  const session = { id: 'sess-local', bridgeSessionId: 'sess-bridge', roleName: 'engineer' };
  const sandbox = {
    activeSess: () => session,
    rt: () => ({ busy: false, lastId: 0 }),
    document: { getElementById: () => ({ checked: false }) },
    bridgeFetch: async (pathName, init) => {
      request = { pathName, init };
      return { roleName: init.body.roleName || null };
    },
    renderSessionList: () => { renderCount++; },
    renderRoleManager: () => {},
    showToast: () => {},
    showChanToast: () => {},
    t: (key) => key,
  };
  vm.createContext(sandbox);
  vm.runInContext(extractFunctionSource(appJs, 'setActiveSessionRole'), sandbox, { filename: appJsPath });
  return { sandbox, session, request: () => request, renderCount: () => renderCount };
}

function loadRoleDeletionHarness() {
  let renderCount = 0;
  const reviewer = { id: 'sess-reviewer', roleName: 'reviewer' };
  const engineer = { id: 'sess-engineer', roleName: 'engineer' };
  const sandbox = {
    state: { sessions: new Map([[reviewer.id, reviewer], [engineer.id, engineer]]) },
    showConfirmDialog: async () => true,
    bridgeFetch: async () => ({ sessionsCleared: 1 }),
    roleProfileName: (name) => String(name || '').trim(),
    loadRoleProfiles: async () => {},
    renderSessionList: () => { renderCount++; },
    showToast: () => {},
    showChanToast: () => {},
    t: (key) => key,
  };
  vm.createContext(sandbox);
  vm.runInContext(extractFunctionSource(appJs, 'deleteRoleProfile'), sandbox, { filename: appJsPath });
  return { sandbox, reviewer, engineer, renderCount: () => renderCount };
}

test('displayTitle adds the current role without changing the content title', () => {
  const { displayTitle } = loadTitleHarness();

  assert.equal(displayTitle({ title: '修复登录超时', roleName: 'engineer' }), '【engineer】修复登录超时');
  assert.equal(displayTitle({ title: '修复登录超时', roleName: null }), '修复登录超时');
});

test('displayTitle decorates generated titles and handles role removal', () => {
  const { displayTitle } = loadTitleHarness();
  const session = {
    title: 'New chat',
    roleName: 'reviewer',
    messages: [{ role: 'user', content: '检查本次发布风险' }],
  };

  assert.equal(displayTitle(session), '【reviewer】检查本次发布风险');
  session.roleName = null;
  assert.equal(displayTitle(session), '检查本次发布风险');
});

test('syncSessionRole refreshes the session list only when the role changes', () => {
  const { sandbox, renderCount } = loadRoleSyncHarness();
  const session = { roleName: 'engineer' };

  sandbox.syncSessionRole(session, { roleName: 'reviewer' });
  assert.equal(session.roleName, 'reviewer');
  assert.equal(renderCount(), 1);

  sandbox.syncSessionRole(session, { roleName: 'reviewer' });
  assert.equal(renderCount(), 1);

  sandbox.syncSessionRole(session, { roleName: null });
  assert.equal(session.roleName, null);
  assert.equal(renderCount(), 2);
});

test('setActiveSessionRole refreshes the displayed title immediately', async () => {
  const { sandbox, session, request, renderCount } = loadRoleSelectionHarness();

  await sandbox.setActiveSessionRole('reviewer');

  assert.equal(session.roleName, 'reviewer');
  assert.equal(request().pathName, '/session/sess-bridge/role');
  assert.equal(request().init.body.roleName, 'reviewer');
  assert.equal(renderCount(), 1);
});

test('deleteRoleProfile removes role prefixes from every loaded session', async () => {
  const { sandbox, reviewer, engineer, renderCount } = loadRoleDeletionHarness();

  await sandbox.deleteRoleProfile('reviewer');

  assert.equal(reviewer.roleName, null);
  assert.equal(engineer.roleName, 'engineer');
  assert.equal(renderCount(), 1);
});
