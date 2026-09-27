"""Real-browser regression scenarios for entry defaults, themes and update status."""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from browser_network import intercept_requests
from playwright.sync_api import expect

VERSION = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
PIXEL = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg==")


def add(page: Any, title: str, url: str, tags: str = "", icon: str = "") -> None:
    page.locator("#addBtn").click()
    page.locator("#title").fill(title)
    page.locator("#url").fill(url)
    page.locator("#tags").fill(tags)
    page.locator("#icon").fill(icon)
    page.locator("#saveBtn").click()
    expect(page.locator("#editor")).not_to_be_visible()


def card(page: Any, title: str) -> Any:
    return page.locator(".card").filter(has=page.get_by_role("heading", name=title, exact=True))


def run_feature_scenarios(browser: Any, server: Any) -> list[str]:
    completed = []
    with server() as base:
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        failures: list[str] = []
        page.on("pageerror", lambda error: failures.append(str(error)))
        external: list[str] = []
        version = {"currentVersion": VERSION, "latestVersion": VERSION, "status": "current", "checkedAt": "2026-09-27T19:00:00Z"}

        def route_request(route):
            url = route.request.url
            if url == base + "/api/version":
                route.fulfill(json=version)
            elif not url.startswith(base):
                external.append(url)
                if "broken.test" in url:
                    route.abort()
                else:
                    route.fulfill(body=PIXEL, content_type="image/png")
            else:
                route.continue_()

        intercept_requests(page, route_request)
        assert page.request.post(base + "/api/import", data={"entries": []}).ok
        page.goto(base)
        expect(page.locator("#versionStatus")).to_have_text("Up to date")
        assert external == []
        add(page, "GitHub saved", "https://github.com/private?token=secret#part")
        expect(card(page, "GitHub saved").locator(".chip")).to_have_text(["development/git", "software/open-source"])
        entry = page.request.get(base + "/api/entries").json()[0]
        assert entry["iconUrl"] == ""
        assert external == []
        page.locator("#remoteIcons").check()
        expect(card(page, "GitHub saved").locator(".icon img")).to_have_attribute("src", "https://github.com/favicon.ico")
        card(page, "GitHub saved").locator(".icon").scroll_into_view_if_needed()
        page.wait_for_function("document.querySelector('.icon img')?.naturalWidth > 0")
        assert external == ["https://github.com/favicon.ico"], external
        add(page, "Custom icon", "https://custom.test/page", "Personal", "https://custom.test/chosen.png")
        expect(card(page, "Custom icon").locator(".icon img")).to_have_attribute("src", "https://custom.test/chosen.png")
        assert "https://custom.test/favicon.ico" not in external
        add(page, "Broken icon", "https://broken.test/path")
        expect(card(page, "Broken icon").locator(".icon .fallback")).to_be_visible()
        card(page, "GitHub saved").get_by_role("button", name="Edit", exact=True).click()
        page.locator("#tags").fill("")
        page.locator("#url").fill("https://python.org/changed")
        page.locator("#saveBtn").click()
        expect(page.locator("#editor")).not_to_be_visible()
        expect(card(page, "GitHub saved").locator(".chip")).to_have_count(0)
        page.reload()
        expect(page.locator("#remoteIcons")).not_to_be_checked()
        expect(card(page, "GitHub saved").locator(".chip")).to_have_count(0)
        completed.append("favicon consent, custom-icon precedence, failed-image fallback and creation-only tags")

        page.locator("#themeBtn").click()
        expect(page.locator("#themePreset option")).to_have_count(21)
        expect(page.locator("#themePreset")).to_have_value("gold-black")
        presets = page.evaluate("KellmarksEnhancements.THEMES.map(t => ({id:t.id, accent:t.colors.accent}))")
        for preset in presets:
            page.locator("#themePreset").select_option(preset["id"])
            assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == preset["accent"]
        page.locator("#themePreset").select_option("forest")
        page.locator("#applyTheme").click()
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", "forest")
        page.locator("#themeBtn").click()
        page.locator("#themePreset").select_option("arctic")
        page.keyboard.press("Escape")
        expect(page.locator("html")).to_have_attribute("data-theme", "forest")
        page.locator("#themeBtn").click()
        page.locator("#themeBackground").evaluate("el => {el.value='#123456'; el.dispatchEvent(new Event('input', {bubbles:true}));}")
        expect(page.locator("#themePreset")).to_have_value("custom")
        page.locator("#applyTheme").click()
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", "custom")
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(18, 52, 86)"
        page.locator("#themeBtn").click()
        page.locator("#themeText").evaluate("el => {el.value='#123456'; el.dispatchEvent(new Event('input', {bubbles:true}));}")
        expect(page.locator("#themeContrast")).to_contain_text("Low text contrast")
        page.locator("#cancelTheme").click()
        page.locator("#themeBtn").click()
        page.locator("#resetTheme").click()
        page.locator("#applyTheme").click()
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", "gold-black")
        completed.append("all 20 presets, custom colors, persistence, cancel, contrast warning and gold/black reset")

        for state, latest, message in [
            ("update_available", "02.01.02", "Update available: v02.01.02"),
            ("ahead", "02.01.00", "Development build"),
            ("no_release", None, "No published stable release"),
            ("unavailable", None, "Update check unavailable"),
            ("current", VERSION, "Up to date"),
        ]:
            version.update(status=state, latestVersion=latest)
            page.locator("#checkVersion").click()
            expect(page.locator("#versionStatus")).to_contain_text(message)
            expect(page.locator("#checkVersion")).to_be_enabled()
        version.update(status="current", latestVersion=None)
        page.locator("#checkVersion").click()
        expect(page.locator("#versionStatus")).to_have_text("Update check unavailable")
        page.evaluate("localStorage.setItem('kellmarks_theme_v1', '{bad json')")
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", "gold-black")
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#themeBtn").click()
        expect(page.locator("#themeDialog")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        screenshot_dir = os.getenv("KELLMARKS_FEATURE_SCREENSHOTS")
        if screenshot_dir:
            page.screenshot(path=str(Path(screenshot_dir) / "kellmarks-theme-mobile.png"), full_page=True)
        page.locator("#cancelTheme").click()
        page.set_viewport_size({"width": 1280, "height": 900})
        if screenshot_dir:
            page.screenshot(path=str(Path(screenshot_dir) / "kellmarks-dashboard.png"), full_page=True)
        assert failures == [], failures
        completed.append("footer current/newer/ahead/offline/missing-release states, corrupt theme storage and mobile layout")
        context.close()

        # Simulate a static host: every API route is unavailable, but local assets remain.
        context = browser.new_context()
        page = context.new_page()
        page.route(base + "/api/**", lambda route: route.fulfill(status=404, json={"error": "no API"}))
        page.goto(base)
        expect(page.locator("#versionStatus")).to_contain_text("requires the server")
        expect(page.locator("#checkVersion")).to_be_disabled()
        add(page, "Static creation", "https://github.com/static")
        expect(card(page, "Static creation").locator(".chip")).to_have_text(["development/git", "software/open-source"])
        card(page, "Static creation").get_by_role("button", name="Edit", exact=True).click()
        page.locator("#tags").fill("")
        page.locator("#saveBtn").click()
        expect(page.locator("#editor")).not_to_be_visible()
        page.reload()
        expect(card(page, "Static creation").locator(".chip")).to_have_count(0)
        context.close()
        completed.append("static-mode creation gets suggestions while edits remain untagged and version status stays honest")

        context = browser.new_context()
        page = context.new_page()
        page.add_init_script("Storage.prototype.getItem = () => {throw new Error('blocked')}; Storage.prototype.setItem = () => {throw new Error('blocked')};")
        page.route(base + "/api/version", lambda route: route.fulfill(json={**version, "status": "unavailable"}))
        page.goto(base)
        page.locator("#themeBtn").click()
        page.locator("#themePreset").select_option("forest")
        page.locator("#applyTheme").click()
        expect(page.locator("#themeContrast")).to_contain_text("Browser storage is unavailable")
        expect(page.locator("html")).to_have_attribute("data-theme", "forest")
        context.close()
        completed.append("blocked browser storage does not stop initialization or temporary theme changes")
    return completed
