"""Real-browser metadata consent and save behavior with a deterministic provider."""
from __future__ import annotations

from typing import Any

from browser_settings import open_settings
from playwright.sync_api import expect

# This script runs only in a disposable browser-test subprocess. Production code
# has no test-provider flag or environment escape hatch for private-site access.
MOCK_SERVER = '''
import os, sys, time
sys.path.insert(0, "docs/server")
import app
from metadata import DescriptionResult

def fetch(url):
    if "/slow" in url:
        time.sleep(0.8)
    if "/missing" in url:
        return DescriptionResult(status="missing")
    return DescriptionResult('Site summary <img src=x onerror=alert(1)> & details', "fetched")

app.app.extensions["kellmarks_description_fetcher"].fetch = fetch
app.app.run(host="127.0.0.1", port=int(os.environ["KELLMARKS_PORT"]),
            debug=False, use_reloader=False)
'''


def add_entry(page: Any, title: str, path: str, description: str = "") -> None:
    page.locator("#addBtn").click()
    page.locator("#title").fill(title)
    page.locator("#url").fill("https://example.test/" + path)
    page.locator("#desc").fill(description)
    page.locator("#saveBtn").click()


def run_metadata_scenarios(browser: Any, server: Any) -> list[str]:
    completed: list[str] = []
    with server(metadata=True) as base:
        context = browser.new_context()
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        writes: list[dict[str, Any]] = []

        def capture(request: Any) -> None:
            if request.method in {"POST", "PUT"} and "/api/entries" in request.url:
                writes.append({"method": request.method, "body": request.post_data_json})

        page.on("request", capture)
        # The only outbound provider is replaced above; version lookup is mocked
        # here so the tests do not make even a fixed GitHub release request.
        page.route(base + "/api/version", lambda route: route.fulfill(json={"status": "unavailable"}))
        page.goto(base)
        expect(page.locator("#autoDescriptions")).to_be_enabled()
        expect(page.locator("#autoDescriptions")).not_to_be_checked()
        add_entry(page, "Default off", "off")
        expect(page.locator("#editor")).not_to_be_visible()
        assert "fetchDescription" not in writes[-1]["body"]
        assert page.request.get(base + "/api/entries").json()[0]["description"] == ""
        completed.append("Description retrieval is off by default and absent from ordinary create requests")

        open_settings(page)
        page.locator("#autoDescriptions").check()
        page.locator("#settingsBtn").click()
        assert len(writes) == 1  # Consent alone does not save or fetch.
        add_entry(page, "Fetched safely", "slow", "   ")
        expect(page.locator("#form")).to_have_attribute("aria-busy", "true")
        expect(page.locator("#saveBtn")).to_be_disabled()
        expect(page.locator("#desc")).to_be_disabled()
        page.keyboard.press("Escape")
        expect(page.locator("#editor")).to_be_visible()
        # A synthetic repeat submission must also be ignored by the busy guard.
        page.locator("#form").dispatch_event("submit")
        expect(page.locator("#editor")).not_to_be_visible()
        assert len(writes) == 2 and writes[-1]["body"]["fetchDescription"] is True
        expect(page.locator("#toast")).to_contain_text("Added with site description")
        card = page.locator(".card").filter(has=page.get_by_role("heading", name="Fetched safely", exact=True))
        expect(card).to_contain_text("Site summary <img src=x onerror=alert(1)> & details")
        expect(card.locator("img")).to_have_count(0)
        assert page.request.get(base + "/api/entries").json()[0]["description"].startswith("Site summary")
        completed.append("Opt-in blank create persists plain-text metadata and prevents duplicate or stale saves")

        add_entry(page, "Manual description", "manual", "Keep my own text")
        expect(page.locator("#editor")).not_to_be_visible()
        assert "fetchDescription" not in writes[-1]["body"]
        assert page.request.get(base + "/api/entries").json()[0]["description"] == "Keep my own text"
        card = page.locator(".card").filter(has=page.get_by_role("heading", name="Fetched safely", exact=True))
        card.get_by_role("button", name="Edit", exact=True).click()
        page.locator("#desc").fill("")
        page.locator("#saveBtn").click()
        expect(page.locator("#editor")).not_to_be_visible()
        assert writes[-1]["method"] == "PUT" and "fetchDescription" not in writes[-1]["body"]
        data = page.request.get(base + "/api/entries").json()
        assert next(item for item in data if item["title"] == "Fetched safely")["description"] == ""
        completed.append("Manual descriptions win and editing an existing blank entry never requests metadata")

        add_entry(page, "No metadata", "missing")
        expect(page.locator("#editor")).not_to_be_visible()
        expect(page.locator("#toast")).to_contain_text("no site description was available")
        assert page.request.get(base + "/api/entries").json()[0]["description"] == ""
        page.reload()
        expect(page.locator("#autoDescriptions")).not_to_be_checked()
        assert len(writes) == 5
        assert errors == [], errors
        context.close()
        completed.append("Missing metadata still saves the bookmark; reload clears description consent")

    with server(external=False, metadata=True) as base:
        page = browser.new_page()
        page.goto(base)
        open_settings(page)
        expect(page.locator("#autoDescriptions")).to_be_disabled()
        # Even a manually forged client flag cannot override server denial.
        response = page.request.post(base + "/api/entries", data={
            "url": "https://example.test/deny", "fetchDescription": True,
        })
        assert response.status == 201 and response.json()["description"] == ""
        assert response.headers["x-kellmarks-description-status"] == "disabled"
        page.close()
        page = browser.new_page()
        page.route(base + "/api/**", lambda route: route.fulfill(status=404, json={"error": "no API"}))
        page.goto(base)
        open_settings(page)
        expect(page.locator("#autoDescriptions")).to_be_disabled()
        page.locator("#settingsBtn").click()
        add_entry(page, "Static save", "static")
        expect(page.locator("#editor")).not_to_be_visible()
        expect(page.locator("#cards")).to_contain_text("Static save")
        page.close()
        completed.append("Operator denial is enforced on the API and browser-only mode offers no network workaround")
    return completed
