"""Settings navigation and browser-only reset regressions against disposable stores."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from playwright.sync_api import expect


def open_settings(page: Any) -> None:
    if page.locator("#settingsBtn").get_attribute("aria-expanded") != "true":
        page.locator("#settingsBtn").click()
    expect(page.locator("#settingsMenu")).to_be_visible()


def choose_setting(page: Any, selector: str) -> None:
    open_settings(page)
    page.locator(selector).click()


def enable_remote_icons(page: Any) -> None:
    open_settings(page)
    page.locator("#remoteIcons").check()
    page.locator("#settingsBtn").click()


def storage_snapshot(page: Any) -> dict[str, Any]:
    return page.evaluate("""() => ({
      local: Object.fromEntries(Object.entries(localStorage)),
      session: Object.fromEntries(Object.entries(sessionStorage))
    })""")


def run_settings_scenarios(browser: Any, server: Any) -> list[str]:
    completed: list[str] = []
    with server(external=False) as base:
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        failures: list[str] = []
        page.on("pageerror", lambda error: failures.append(str(error)))
        entry = {"id": "keep", "title": "Keep on server", "url": "https://example.test/keep"}
        assert page.request.post(base + "/api/import", data={"entries": [entry]}).ok
        page.goto(base)
        expect(page.locator("#cards h3")).to_have_text("Keep on server")
        expect(page.locator("header .version-badge")).to_have_count(0)
        expect(page.locator("#versionCurrent")).to_contain_text("Kellmarks v")
        expect(page.locator("#settingsMenu")).not_to_be_visible()
        expect(page.locator("aside #importBtn, aside #exportBtn, .library-tools #remoteIcons")).to_have_count(0)
        page.locator("#settingsBtn").focus()
        page.keyboard.press("Enter")
        expect(page.locator("#themeBtn")).to_be_focused()
        page.keyboard.press("Escape")
        expect(page.locator("#settingsBtn")).to_be_focused()
        expect(page.locator("#settingsBtn")).to_have_attribute("aria-expanded", "false")
        open_settings(page)
        page.locator("#q").click()
        expect(page.locator("#settingsMenu")).not_to_be_visible()
        open_settings(page)
        for _ in range(4):  # Theme, import, export, clear; disabled icons are skipped.
            page.keyboard.press("Tab")
        expect(page.locator("#settingsMenu")).not_to_be_visible()
        completed.append("Settings placement, footer-only version, keyboard and outside-click dismissal")

        choose_setting(page, "#themeBtn")
        page.locator("#themePreset").select_option("mono-amber")
        page.locator("#applyTheme").click()
        expect(page.locator("#themeBtn")).to_be_focused()
        expect(page.locator("html")).to_have_attribute("data-theme", "mono-amber")
        with page.expect_download() as download:
            choose_setting(page, "#exportBtn")
        exported = json.loads(Path(download.value.path()).read_text())
        assert exported["entries"][0]["id"] == "keep"
        # Exercise the actual input-opening button, rather than bypassing it.
        open_settings(page)
        with page.expect_file_chooser() as chooser:
            page.locator("#importBtn").click()
        chooser.value.set_files({"name": "links.json", "mimeType": "application/json",
                                 "buffer": json.dumps(exported).encode()})
        expect(page.locator("#applyImport")).to_be_enabled()
        page.locator("#cancelImport").click()
        expect(page.locator("#importBtn")).to_be_focused()
        completed.append("Theme persistence, JSON download, actual import file chooser and focus restoration")

        page.evaluate("""() => {
          localStorage.setItem('kellmarks_local_fallback_v2', '[{"title":"Browser only"}]');
          localStorage.setItem('kellmarks_legacy_test', '{corrupt');
          localStorage.setItem('other_app', 'keep-local');
          sessionStorage.setItem('kellmarks_api_token_v1', 'test-session-value');
          sessionStorage.setItem('other_app', 'keep-session');
        }""")
        before = storage_snapshot(page)
        for cancel in ["#cancelClearMemory", "#closeClearMemory", "Escape"]:
            choose_setting(page, "#clearMemoryBtn")
            expect(page.locator("#cancelClearMemory")).to_be_focused()
            if cancel == "Escape":
                page.keyboard.press("Escape")
            else:
                page.locator(cancel).click()
            expect(page.locator("#clearMemoryDialog")).not_to_be_visible()
            expect(page.locator("#clearMemoryBtn")).to_be_focused()
            assert storage_snapshot(page) == before
        server_before = page.request.get(base + "/api/entries").json()
        writes: list[str] = []
        page.on("request", lambda request: writes.append(request.url) if request.method in {"POST", "PUT", "PATCH", "DELETE"} else None)
        choose_setting(page, "#clearMemoryBtn")
        with page.expect_navigation(wait_until="load"):
            page.locator("#confirmClearMemory").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "gold-black")
        expect(page.locator("#remoteIcons")).not_to_be_checked()
        expect(page.locator("#settingsMenu")).not_to_be_visible()
        expect(page.locator("#cards h3")).to_have_text("Keep on server")
        assert storage_snapshot(page) == {"local": {"other_app": "keep-local"}, "session": {"other_app": "keep-session"}}
        assert page.request.get(base + "/api/entries").json() == server_before
        assert writes == []
        completed.append("Reset cancellation, scoped storage removal, default theme and server-data preservation")

        page.evaluate("""() => {
          localStorage.setItem('kellmarks_theme_v1', '{bad json');
          sessionStorage.setItem('kellmarks_api_token_v1', 'test-session-value');
          Storage.prototype.removeItem = function () { throw new Error('blocked'); };
        }""")
        before = storage_snapshot(page)
        choose_setting(page, "#clearMemoryBtn")
        page.locator("#confirmClearMemory").click()
        expect(page.locator("#clearMemoryStatus")).to_contain_text("could not be cleared")
        expect(page.locator("#clearMemoryDialog")).to_be_visible()
        assert storage_snapshot(page) == before
        page.locator("#cancelClearMemory").click()
        page.reload()
        completed.append("Blocked storage reports failure without reloading or claiming success")

        for width in [320, 390, 768]:
            page.set_viewport_size({"width": width, "height": 700})
            open_settings(page)
            box = page.locator("#settingsMenu").bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= width
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            choose_setting(page, "#clearMemoryBtn")
            expect(page.locator("#cancelClearMemory")).to_be_visible()
            expect(page.locator("#confirmClearMemory")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#cancelClearMemory").click()
            page.locator("#settingsBtn").click()
        screenshot_dir = os.getenv("KELLMARKS_FEATURE_SCREENSHOTS")
        if screenshot_dir:
            page.set_viewport_size({"width": 1280, "height": 900})
            open_settings(page)
            page.screenshot(path=str(Path(screenshot_dir) / "kellmarks-settings.png"), full_page=True)
            choose_setting(page, "#clearMemoryBtn")
            page.screenshot(path=str(Path(screenshot_dir) / "kellmarks-clear-memory.png"), full_page=True)
        assert failures == [], failures
        context.close()
        completed.append("Settings and confirmation fit 320px, 390px and tablet viewports")

        context = browser.new_context()
        page = context.new_page()
        page.route(base + "/api/**", lambda route: route.fulfill(status=404, json={"error": "no API"}))
        page.goto(base)
        page.locator("#addBtn").click()
        page.locator("#title").fill("Only in this browser")
        page.locator("#url").fill("https://local-only.test/bookmark")
        page.locator("#saveBtn").click()
        expect(page.locator("#editor")).not_to_be_visible()
        expect(page.locator("#cards")).to_contain_text("Only in this browser")
        with page.expect_download() as download:
            choose_setting(page, "#exportBtn")
        exported = json.loads(Path(download.value.path()).read_text())
        assert any(item["title"] == "Only in this browser" for item in exported["entries"])
        choose_setting(page, "#importBtn")
        expect(page.locator("#toast")).to_contain_text("requires the local server")
        choose_setting(page, "#clearMemoryBtn")
        with page.expect_navigation(wait_until="load"):
            page.locator("#confirmClearMemory").click()
        expect(page.locator("#cards")).not_to_contain_text("Only in this browser")
        assert page.evaluate("localStorage.getItem('kellmarks_local_fallback_v2')") is None
        context.close()
        completed.append("Static-mode JSON backup and confirmed removal of browser-only bookmarks")
    return completed
