"""Unit-тесты для backend/scripts/post-build.cjs.

Запускает скрипт через subprocess на временной директории dist/
и проверяет, что HTML-файлы корректно модифицируются.

post-build.cjs НЕ добавляет data-editable-id (это делает pre-build.cjs).
Он только инжектирует click/highlight listener перед </body>.

Запуск:
    cd backend
    pytest tests/test_post_build_js.py -v
"""
import subprocess
import re
from pathlib import Path

import pytest

POST_BUILD_JS = Path(__file__).resolve().parent.parent / "scripts" / "post-build.cjs"


def run_script(dist_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", str(POST_BUILD_JS)],
        cwd=str(dist_dir.parent),   # dist/ лежит в cwd
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Фикстура: временная dist/ директория
# ---------------------------------------------------------------------------

@pytest.fixture()
def dist(tmp_path: Path) -> Path:
    d = tmp_path / "dist"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# postMessage listener инжектируется
# ---------------------------------------------------------------------------

class TestListenerInjection:

    def test_script_injected_before_body_close(self, dist):
        (dist / "index.html").write_text(
            "<html><body><h1>Hi</h1></body></html>", encoding="utf-8"
        )
        run_script(dist)
        html = (dist / "index.html").read_text(encoding="utf-8")
        assert "<script>" in html
        assert "window.parent.postMessage" in html
        script_pos = html.index("<script>")
        body_close_pos = html.index("</body>")
        assert script_pos < body_close_pos

    def test_listener_contains_element_selected_type(self, dist):
        (dist / "index.html").write_text(
            "<html><body></body></html>", encoding="utf-8"
        )
        run_script(dist)
        html = (dist / "index.html").read_text(encoding="utf-8")
        assert "element-selected" in html

    def test_listener_contains_element_deselected_type(self, dist):
        """Деселект при повторном клике или клике в пустое место."""
        (dist / "index.html").write_text(
            "<html><body></body></html>", encoding="utf-8"
        )
        run_script(dist)
        html = (dist / "index.html").read_text(encoding="utf-8")
        assert "element-deselected" in html

    def test_listener_sends_outer_html(self, dist):
        """outerHTML выбранного элемента включается в postMessage."""
        (dist / "index.html").write_text(
            "<html><body></body></html>", encoding="utf-8"
        )
        run_script(dist)
        html = (dist / "index.html").read_text(encoding="utf-8")
        assert "outerHTML" in html

    def test_listener_handles_highlight_message(self, dist):
        """Listener умеет получать highlight-element от родителя."""
        (dist / "index.html").write_text(
            "<html><body></body></html>", encoding="utf-8"
        )
        run_script(dist)
        html = (dist / "index.html").read_text(encoding="utf-8")
        assert "highlight-element" in html

    def test_listener_uses_closest_selector(self, dist):
        (dist / "index.html").write_text(
            "<html><body></body></html>", encoding="utf-8"
        )
        run_script(dist)
        html = (dist / "index.html").read_text(encoding="utf-8")
        assert "closest('[data-editable-id]')" in html

    def test_listener_injected_only_once(self, dist):
        """Если запустить скрипт один раз — должен быть ровно один блок listener'а.
        Проверяем по числу вхождений строки-маркера начала IIFE."""
        (dist / "index.html").write_text(
            "<html><body><h1>X</h1></body></html>", encoding="utf-8"
        )
        run_script(dist)
        html = (dist / "index.html").read_text(encoding="utf-8")
        assert html.count("(function ()") == 1

    def test_prevent_default_called_on_click(self, dist):
        (dist / "index.html").write_text(
            "<html><body></body></html>", encoding="utf-8"
        )
        run_script(dist)
        html = (dist / "index.html").read_text(encoding="utf-8")
        assert "e.preventDefault()" in html


# ---------------------------------------------------------------------------
# Обход файлов
# ---------------------------------------------------------------------------

class TestFileWalking:

    def test_processes_multiple_html_files(self, dist):
        (dist / "index.html").write_text(
            "<html><body><h1>Home</h1></body></html>", encoding="utf-8"
        )
        about = dist / "about"
        about.mkdir()
        (about / "index.html").write_text(
            "<html><body><h1>About</h1></body></html>", encoding="utf-8"
        )
        result = run_script(dist)
        assert "processing 2 HTML file(s)" in result.stdout

    def test_non_html_files_are_ignored(self, dist):
        (dist / "index.html").write_text(
            "<html><body><h1>Hi</h1></body></html>", encoding="utf-8"
        )
        (dist / "style.css").write_text("body {}", encoding="utf-8")
        (dist / "app.js").write_text("console.log(1)", encoding="utf-8")
        run_script(dist)
        assert (dist / "style.css").read_text() == "body {}"
        assert (dist / "app.js").read_text() == "console.log(1)"

    def test_script_exits_zero(self, dist):
        (dist / "index.html").write_text(
            "<html><body></body></html>", encoding="utf-8"
        )
        result = run_script(dist)
        assert result.returncode == 0

    def test_stdout_reports_done(self, dist):
        (dist / "index.html").write_text(
            "<html><body></body></html>", encoding="utf-8"
        )
        result = run_script(dist)
        assert "post-build: done" in result.stdout

    def test_missing_dist_dir_exits_nonzero(self, tmp_path):
        """Если dist/ нет — process.exit(1)."""
        result = subprocess.run(
            ["node", str(POST_BUILD_JS)],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
