import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const appJsPath = path.resolve('frontends/desktop/static/app.js');
const appJs = fs.readFileSync(appJsPath, 'utf8');

function extractFunctionSource(source, name) {
  const marker = `function ${name}`;
  const start = source.indexOf(marker);
  if (start < 0) return '';
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

function loadImageRendererHelpers() {
  const sandbox = {
    URL,
    document: {
      createElement(tag) {
        if (tag !== 'div') throw new Error(`unexpected element ${tag}`);
        return {
          _text: '',
          set textContent(value) { this._text = String(value ?? ''); },
          get innerHTML() {
            return this._text
              .replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;');
          },
        };
      },
    },
  };
  vm.createContext(sandbox);

  const helperNames = [
    'cleanMarkdownImageUrl',
    'escapeHtml',
    'isLikelyMarkdownImageUrl',
    'extractLikelyMarkdownImageUrls',
    'autoEmbedMarkdownImageUrls',
    'renderedImageSrcSet',
    'renderToolResultImagePreviews',
    'renderTurnBodyWithImageFallback',
  ];
  const helperSource = helperNames
    .map((name) => extractFunctionSource(appJs, name))
    .filter(Boolean)
    .join('\n');
  vm.runInContext(helperSource, sandbox, { filename: appJsPath });

  sandbox.renderTurnBody = (body) => sandbox
    .autoEmbedMarkdownImageUrls(String(body || ''))
    .replace(/!\[[^\]\n]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)/g, (_, url) => (
      `<p><img src="${sandbox.escapeHtml(url)}" alt="image"></p>`
    ));
  return sandbox;
}

function imgCount(html) {
  return (String(html).match(/<img\b/g) || []).length;
}

test('plain generated image URL is rendered once', () => {
  const helpers = loadImageRendererHelpers();
  const url = 'https://example.test/v1/files/image?id=ship';

  const html = helpers.renderTurnBodyWithImageFallback(`已生成:\n${url}`);

  assert.equal(imgCount(html), 1);
});

test('code-block image URL still receives one fallback preview', () => {
  const helpers = loadImageRendererHelpers();
  const url = 'https://example.test/v1/files/image?id=ship';
  helpers.renderTurnBody = () => `<pre>{"urls":["${url}"]}</pre>`;

  const html = helpers.renderTurnBodyWithImageFallback(`\`\`\`json\n{"urls":["${url}"]}\n\`\`\``);

  assert.equal(imgCount(html), 1);
  assert.match(html, /tool-result-images/);
});
