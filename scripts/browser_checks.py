"""Exercise the real dashboard against isolated local stores and mocked external results."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from browser_enhancements import run_feature_scenarios
from browser_metadata import MOCK_SERVER, run_metadata_scenarios
from browser_network import intercept_requests
from browser_retro_cards import run_retro_card_scenarios
from browser_settings import enable_remote_icons, run_settings_scenarios
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def server(external: bool = True, metadata: bool = False):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="kellmarks-browser-") as directory:
        environment = dict(os.environ)
        for key in list(environment):
            if key.startswith("KELLMARKS_"):
                environment.pop(key)
        environment.update({
            "KELLMARKS_DATA_FILE": str(Path(directory) / "data.json"),
            "KELLMARKS_LEGACY_DATA_FILE": str(Path(directory) / "missing.json"),
            "KELLMARKS_PORT": str(port),
            "KELLMARKS_EXTERNAL_REQUESTS": "1" if external else "0",
        })
        with (Path(directory) / "server.log").open("w+") as log:
            process = subprocess.Popen(  # noqa: S603
                [os.getenv("KELLMARKS_TEST_PYTHON", sys.executable),
                 *(["-c", MOCK_SERVER] if metadata else ["docs/server/app.py"])],
                cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.05)
                else:
                    raise RuntimeError("Test server failed to start")
                yield f"http://127.0.0.1:{port}"
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def bookmark(url: str, title: str, **fields: Any) -> dict[str, Any]:
    return {"url": url, "title": title, **fields}


def choose_file(page: Any, data: Any, name: str = "bookmarks.json") -> None:
    body = data if isinstance(data, str) else json.dumps(data)
    page.locator("#filePick").set_input_files({
        "name": name,
        "mimeType": "text/html" if name.endswith(".html") else "application/json",
        "buffer": body.encode(),
    })
    expect(page.locator("#importDialog")).to_be_visible()


def main() -> None:
    completed: list[str] = []
    with sync_playwright() as playwright:
        executable = os.getenv("KELLMARKS_BROWSER_EXECUTABLE")
        # Use full Chromium's headless mode for native background-tab gestures.
        # The install command already provides this browser alongside headless shell.
        options = {"executable_path": executable} if executable else {"channel": "chromium"}
        browser = playwright.chromium.launch(headless=True, **options)
        try:
            with server() as base:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                failures: list[str] = []
                page.on("pageerror", lambda error: failures.append(str(error)))
                external: list[str] = []
                lookups: list[str] = []

                def routing(route):
                    url = route.request.url
                    if url.startswith(base + "/api/external/ddg"):
                        lookups.append(url)
                        route.fulfill(json={"results": [{"url": "https://example.test/result", "title": "Mock result"}]})
                    elif url == base + "/api/version":
                        version = (ROOT / "VERSION").read_text().strip()
                        route.fulfill(json={"currentVersion": version, "latestVersion": version, "status": "current", "checkedAt": None})
                    elif not url.startswith(base):
                        external.append(url)
                        route.abort()
                    else:
                        route.continue_()

                intercept_requests(page, routing)
                initial = [
                    bookmark("https://a.test/", "Alpha", id="alpha", iconUrl="https://icons.test/a.png", createdAt="2020-01-01T00:00:00Z", updatedAt="2026-09-20T00:00:00Z"),
                    bookmark("https://z.test/", "Zulu", id="zulu", createdAt="2026-09-27T00:00:00Z", updatedAt="2026-09-01T00:00:00Z"),
                ]
                assert page.request.post(base + "/api/import", data={"entries": initial}).ok
                page.goto(base)
                expect(page.locator("#cards h3")).to_have_text(["Alpha", "Zulu"])
                expect(page.locator("#remoteIcons")).not_to_be_checked()
                assert external == [] and lookups == []
                page.locator("#sortOrder").select_option("createdAt")
                expect(page.locator("#cards h3")).to_have_text(["Zulu", "Alpha"])
                page.locator("#sortOrder").select_option("updatedAt")
                expect(page.locator("#cards h3")).to_have_text(["Alpha", "Zulu"])
                page.locator("#q").fill("Alpha")
                expect(page.locator("#viewMeta")).to_contain_text('for "Alpha"')
                assert lookups == []
                page.locator("#webSearchBtn").click()
                expect(page.locator("#ddgList")).to_contain_text("Mock result")
                assert len(lookups) == 1
                page.locator("#q").fill("")
                expect(page.locator("#cards h3")).to_have_count(2)
                enable_remote_icons(page)
                # Icons are lazy-loaded; request completion is not a 150 ms guarantee.
                for icon in page.locator(".icon").all():
                    icon.scroll_into_view_if_needed()
                expect(page.locator(".icon .fallback")).to_have_count(2)
                assert set(external) == {"https://icons.test/a.png", "https://z.test/favicon.ico"}, external
                page.reload()
                expect(page.locator("#remoteIcons")).not_to_be_checked()
                expect(page.locator("#cards h3")).to_have_count(2)
                assert len(external) == 2
                completed.append("sorting, explicit web search, session-only icon consent")

                incoming = [bookmark("https://a.test/", "New title", tags=["research"]), bookmark("https://new.test/", "New bookmark")]
                choose_file(page, incoming)
                expect(page.locator("#applyImport")).to_be_enabled()
                expect(page.locator("#importMode")).to_have_value("merge")
                expect(page.locator("#importSummary")).to_contain_text("1 new, 1 matching URLs")
                assert len(page.request.get(base + "/api/entries").json()) == 2
                page.locator("#importTitleSource").select_option("incoming")
                expect(page.locator("#applyImport")).to_be_disabled()
                page.locator("#previewImport").click()
                expect(page.locator("#applyImport")).to_be_enabled()
                page.locator("#applyImport").click()
                expect(page.locator("#importDialog")).not_to_be_visible()
                expect(page.locator("#cards h3")).to_have_count(3)
                entries = page.request.get(base + "/api/entries").json()
                first = next(item for item in entries if item["id"] == "alpha")
                assert first["title"] == "New title" and first["tags"] == ["research"]
                assert any(item["id"] == "zulu" for item in entries)
                completed.append("reviewed merge preserves existing entries and applies selected fields")

                choose_file(page, [bookmark("javascript:alert(1)", "Unsafe")])
                expect(page.locator("#importSummary")).to_contain_text("1 invalid entries")
                expect(page.locator("#applyImport")).to_be_disabled()
                page.locator("#cancelImport").click()
                choose_file(page, [bookmark("https://later.test/", "Later")])
                expect(page.locator("#applyImport")).to_be_enabled()
                assert page.request.post(base + "/api/entries", data=bookmark("https://concurrent.test/", "Concurrent")).ok
                page.locator("#applyImport").click()
                expect(page.locator("#importSummary")).to_contain_text("library changed")
                expect(page.locator("#applyImport")).to_be_disabled()
                assert len(page.request.get(base + "/api/entries").json()) == 4
                page.locator("#cancelImport").click()
                completed.append("invalid input and concurrent writes cannot silently replace the library")

                html = '<DL><DT><H3>Research</H3><DL><DT><A HREF="https://html.test/">&lt;script&gt;not executable&lt;/script&gt;</A></DL></DL>'
                choose_file(page, html, "browser.html")
                expect(page.locator("#applyImport")).to_be_enabled()
                page.locator("#applyImport").click()
                expect(page.locator("#importDialog")).not_to_be_visible()
                assert any(item["tags"] == ["Research"] for item in page.request.get(base + "/api/entries").json())
                assert len(external) == 2
                completed.append("browser HTML import is text-only and maps folders to tags")

                choose_file(page, [])
                expect(page.locator("#applyImport")).to_be_enabled()
                page.locator("#importMode").select_option("replace")
                page.locator("#previewImport").click()
                expect(page.locator("#applyImport")).to_be_enabled()
                page.once("dialog", lambda dialog: dialog.dismiss())
                page.locator("#applyImport").click()
                assert len(page.request.get(base + "/api/entries").json()) == 5
                page.once("dialog", lambda dialog: dialog.accept())
                page.locator("#applyImport").click()
                expect(page.locator("#importDialog")).not_to_be_visible()
                assert page.request.get(base + "/api/entries").json() == []
                completed.append("empty replacement requires explicit action and confirmation")

                page.set_viewport_size({"width": 390, "height": 844})
                page.locator("#addBtn").click()
                expect(page.locator("#editor")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.locator("#cancelBtn").click()
                assert failures == [], failures
                completed.append("mobile layout and editor remain usable without JavaScript errors")
                screenshot = os.getenv("KELLMARKS_BROWSER_SCREENSHOT")
                if screenshot:
                    page.screenshot(path=screenshot, full_page=True)
                page.close()

            with server(external=False) as base:
                page = browser.new_page()
                page.goto(base)
                expect(page.locator("#privacyNotice")).to_contain_text("External requests are disabled")
                page.locator("#q").fill("private query")
                expect(page.locator("#viewMeta")).to_contain_text("private query")
                expect(page.locator("#webSearchBtn")).to_be_disabled()
                expect(page.locator("#remoteIcons")).to_be_disabled()
                assert page.request.get(base + "/api/external/ddg?q=private").status == 403
                expect(page.locator("#versionStatus")).to_contain_text("disabled by operator")
                assert page.request.get(base + "/api/version").json()["status"] == "disabled"
                page.close()
                completed.append("operator denial overrides all dashboard external controls")
            completed.extend(run_feature_scenarios(browser, server))
            completed.extend(run_retro_card_scenarios(browser, server))
            completed.extend(run_settings_scenarios(browser, server))
            completed.extend(run_metadata_scenarios(browser, server))
        finally:
            browser.close()
    print(json.dumps({"browserScenariosPassed": len(completed), "scenarios": completed}, indent=2))


if __name__ == "__main__":
    main()
