// Обходит src/, добавляет data-editable-id + data-editable-file к HTML-тегам
// в .astro файлах ДО сборки. Атрибуты переживают Astro build и остаются в dist/.
//
// ID детерминированы: sha256(relPath:tagIndex).slice(0,16) — стабильны между ребилдами,
// пока структура файла не меняется кардинально.
const { readdirSync, readFileSync, writeFileSync, statSync } = require('fs');
const { join, relative } = require('path');
const { createHash } = require('crypto');

const SRC_DIR = join(process.cwd(), 'src');

// Только строчные HTML-теги — не Astro-компоненты (<Nav />, <Footer />)
const TAG_RE = /<(p|h[1-6]|section|div|button|a|img)(\s[^>]*)?(\/?)>/gi;

function stableId(relPath, idx) {
  return createHash('sha256').update(`${relPath}:${idx}`).digest('hex').slice(0, 16);
}

function addEditableAttrs(content, relPath) {
  let idx = 0;
  return content.replace(TAG_RE, (match, tag, attrs, selfClose) => {
    const currentIdx = idx++; // всегда инкрементируем — сохраняем нумерацию
    if (attrs && /data-editable-id/i.test(attrs)) return match;
    const id = stableId(relPath, currentIdx);
    const safeAttrs = (attrs || '').replace(/\s*\/$/, '');
    const close = selfClose ? ' /' : '';
    return `<${tag}${safeAttrs} data-editable-id="${id}" data-editable-file="${relPath}"${close}>`;
  });
}

function walk(dir) {
  const entries = readdirSync(dir);
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      files.push(...walk(full));
    } else if (entry.endsWith('.astro') || entry.endsWith('.html')) {
      files.push(full);
    }
  }
  return files;
}

try {
  const srcFiles = walk(SRC_DIR);
  console.log(`pre-build: processing ${srcFiles.length} source file(s)`);

  for (const file of srcFiles) {
    const relPath = relative(SRC_DIR, file).replace(/\\/g, '/');
    let content = readFileSync(file, 'utf8');
    const before = (content.match(TAG_RE) || []).length;
    content = addEditableAttrs(content, relPath);
    writeFileSync(file, content, 'utf8');
    console.log(`  processed: ${relPath} (${before} tag(s))`);
  }

  console.log('pre-build: done');
} catch (err) {
  console.error('pre-build: FATAL ERROR', err);
  process.exit(1);
}
