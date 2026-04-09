// Обходит dist/, инжектирует postMessage listener перед </body>.
// data-editable-id и data-editable-file уже добавлены pre-build.cjs в src/.
const { readdirSync, readFileSync, writeFileSync, statSync } = require('fs');
const { join } = require('path');

const DIST_DIR = join(process.cwd(), 'dist');

const LISTENER_SCRIPT = `<script>
(function () {
  var _currentId = null;

  // Подсветка по запросу от родителя (PreviewPanel)
  window.addEventListener('message', function (e) {
    if (!e.data || e.data.type !== 'highlight-element') return;
    var prev = document.querySelector('[data-editable-highlighted]');
    if (prev) {
      prev.style.outline = '';
      prev.style.outlineOffset = '';
      prev.removeAttribute('data-editable-highlighted');
    }
    if (e.data.editable_id) {
      var el = document.querySelector('[data-editable-id="' + e.data.editable_id + '"]');
      if (el) {
        el.style.outline = '2px solid #6366f1';
        el.style.outlineOffset = '2px';
        el.setAttribute('data-editable-highlighted', '');
      }
    }
  });

  // Клик на элемент → postMessage в родителя
  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-editable-id]');

    if (!el) {
      // Клик в пустое место → снять выделение
      if (_currentId !== null) {
        _currentId = null;
        window.parent.postMessage({ type: 'element-deselected' }, '*');
      }
      return;
    }

    e.preventDefault();

    if (el.dataset.editableId === _currentId) {
      // Повторный клик на тот же элемент → деселект
      _currentId = null;
      window.parent.postMessage({ type: 'element-deselected' }, '*');
    } else {
      _currentId = el.dataset.editableId;
      // Temporarily strip highlight styles before capturing outerHTML
      // so the AI doesn't preserve the debug outline in the source file
      var prevOutline = el.style.outline;
      var prevOutlineOffset = el.style.outlineOffset;
      el.style.outline = '';
      el.style.outlineOffset = '';
      var html = el.outerHTML;
      el.style.outline = prevOutline;
      el.style.outlineOffset = prevOutlineOffset;
      window.parent.postMessage({
        type: 'element-selected',
        editable_id: el.dataset.editableId,
        file_path: el.dataset.editableFile || '',
        element_html: html,
      }, '*');
    }
  });
})();
</script>`;

function injectListener(content) {
  return content.replace(/<\/body>/i, `${LISTENER_SCRIPT}\n</body>`);
}

function walk(dir) {
  const entries = readdirSync(dir);
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      files.push(...walk(full));
    } else if (entry.endsWith('.html')) {
      files.push(full);
    }
  }
  return files;
}

try {
  const htmlFiles = walk(DIST_DIR);
  console.log(`post-build: processing ${htmlFiles.length} HTML file(s)`);

  for (const file of htmlFiles) {
    let content = readFileSync(file, 'utf8');
    content = injectListener(content);
    writeFileSync(file, content, 'utf8');
    console.log(`  processed: ${file}`);
  }

  console.log('post-build: done');
} catch (err) {
  console.error('post-build: FATAL ERROR', err);
  process.exit(1);
}
