import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const appJsPath = path.resolve('frontends/desktop/static/app.js');
const appJs = fs.readFileSync(appJsPath, 'utf8');
const styles = fs.readFileSync(path.resolve('frontends/desktop/static/styles.css'), 'utf8');
const markup = fs.readFileSync(path.resolve('frontends/desktop/static/index.html'), 'utf8');

function extractFunctionSource(source, name) {
  const marker = `function ${name}`;
  let start = source.indexOf(marker);
  if (start < 0) return '';
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

function classList() {
  const values = new Set();
  return {
    add: (...names) => names.forEach(name => values.add(name)),
    contains: (name) => values.has(name),
    remove: (...names) => names.forEach(name => values.delete(name)),
    toggle: (name) => {
      if (values.has(name)) {
        values.delete(name);
        return false;
      }
      values.add(name);
      return true;
    },
  };
}

function button() {
  const attributes = new Map();
  return {
    setAttribute: (name, value) => attributes.set(name, String(value)),
    getAttribute: (name) => attributes.get(name),
  };
}

function focusTarget() {
  let focusCount = 0;
  return {
    focus: () => { focusCount++; },
    focusCount: () => focusCount,
  };
}

function loadDrawerHarness(mobile) {
  const sidebarButton = button();
  const sessionButton = button();
  const sidebarDrawer = focusTarget();
  const sessionDrawer = focusTarget();
  const sandbox = {
    bodyEl: { classList: classList() },
    mainPanel: {},
    sbPanel: sidebarDrawer,
    rpPanel: sessionDrawer,
    mobileDrawerMedia: { matches: mobile },
    mobileDrawerTrigger: null,
    window: { setTimeout: (callback) => callback() },
    document: {
      querySelectorAll: (selector) => selector === '.pt-sb-toggle' ? [sidebarButton] : [sessionButton],
      activeElement: null,
    },
  };
  vm.createContext(sandbox);
  vm.runInContext([
    extractFunctionSource(appJs, 'usesMobileDrawers'),
    extractFunctionSource(appJs, 'mobileDrawerPanel'),
    extractFunctionSource(appJs, 'focusMobileDrawer'),
    extractFunctionSource(appJs, 'syncShellToggleAria'),
    extractFunctionSource(appJs, 'closeMobileDrawers'),
    extractFunctionSource(appJs, 'toggleShellPanel'),
  ].join('\n'), sandbox, { filename: appJsPath });
  return { sandbox, sidebarButton, sessionButton, sidebarDrawer, sessionDrawer };
}

test('mobile toolbar toggles one drawer at a time and updates aria state', () => {
  const { sandbox, sidebarButton, sessionButton, sidebarDrawer, sessionDrawer } = loadDrawerHarness(true);
  const sidebarTrigger = focusTarget();
  const sessionTrigger = focusTarget();
  sandbox.syncShellToggleAria();
  assert.equal(sidebarButton.getAttribute('aria-expanded'), 'false');
  assert.equal(sessionButton.getAttribute('aria-expanded'), 'false');

  sandbox.toggleShellPanel('sidebar', sidebarTrigger);
  assert.equal(sandbox.bodyEl.classList.contains('sb-mobile-open'), true);
  assert.equal(sandbox.bodyEl.classList.contains('rp-mobile-open'), false);
  assert.equal(sandbox.mainPanel.inert, true);
  assert.equal(sidebarDrawer.focusCount(), 1);
  assert.equal(sidebarButton.getAttribute('aria-expanded'), 'true');
  assert.equal(sessionButton.getAttribute('aria-expanded'), 'false');

  sandbox.toggleShellPanel('sessions', sessionTrigger);
  assert.equal(sandbox.bodyEl.classList.contains('sb-mobile-open'), false);
  assert.equal(sandbox.bodyEl.classList.contains('rp-mobile-open'), true);
  assert.equal(sessionDrawer.focusCount(), 1);
  assert.equal(sidebarButton.getAttribute('aria-expanded'), 'false');
  assert.equal(sessionButton.getAttribute('aria-expanded'), 'true');

  sandbox.closeMobileDrawers();
  assert.equal(sandbox.bodyEl.classList.contains('sb-mobile-open'), false);
  assert.equal(sandbox.bodyEl.classList.contains('rp-mobile-open'), false);
  assert.equal(sandbox.mainPanel.inert, false);
  assert.equal(sessionTrigger.focusCount(), 1);
});

test('desktop toolbar retains the collapsed-panel behavior', () => {
  const { sandbox, sidebarButton, sessionButton } = loadDrawerHarness(false);

  sandbox.toggleShellPanel('sidebar');
  assert.equal(sandbox.bodyEl.classList.contains('sb-collapsed'), true);
  assert.equal(sidebarButton.getAttribute('aria-expanded'), 'false');
  assert.equal(sessionButton.getAttribute('aria-expanded'), 'true');

  sandbox.toggleShellPanel('sidebar');
  assert.equal(sandbox.bodyEl.classList.contains('sb-collapsed'), false);
  assert.equal(sidebarButton.getAttribute('aria-expanded'), 'true');
});

test('mobile styles expose the panels as drawers instead of permanently hiding them', () => {
  assert.match(markup, /id="sidebar"/);
  assert.match(markup, /id="mobile-drawer-scrim"/);
  assert.match(styles, /\.body\.sb-mobile-open \.sidebar/);
  assert.match(styles, /\.body\.rp-mobile-open \.rightpanel/);
  assert.match(styles, /\.mobile-drawer-scrim\{/);
  assert.doesNotMatch(styles, /\.sidebar,\s*\.rightpanel,\s*\.sb-resize,\s*\.rp-resize\s*\{\s*display:\s*none !important;/);
});
