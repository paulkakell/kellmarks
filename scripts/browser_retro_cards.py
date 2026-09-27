"""Real-browser regression checks for monitor themes and native card links."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from playwright.sync_api import expect


def card(page: Any, title: str) -> Any:
    return page.locator(".card").filter(has=page.get_by_role("heading", name=title, exact=True))


def center(locator: Any) -> tuple[float, float]:
    box = locator.bounding_box()
    assert box is not None
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def settle(page: Any) -> None:
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def point_over_link(page: Any, locator: Any, target: str) -> tuple[float, float]:
    """Raw mouse/touch coordinates need visible hit targets, unlike locator.click."""
    page.bring_to_front()
    locator.evaluate("el => el.closest('.card').scrollIntoView({block:'center', inline:'nearest'})")
    settle(page)
    point = center(locator)
    hit = page.evaluate("""([x,y]) => {
        const element = document.elementFromPoint(x,y);
        return {href: element?.closest('a')?.getAttribute('href'),
                element: element?.outerHTML, point: [x,y], scrollY};
    }""", point)
    assert hit.get("href") == target, hit
    return point


def opened_page(context: Any, page: Any, action: Any, target: str) -> None:
    """Check a real browser navigation, not a mocked window.open call."""
    # Native middle/modifier clicks can create background tabs without an
    # opener relationship. Observe all pages while still asserting real navigation.
    with context.expect_page() as opened:
        action()
    popup = opened.value
    expect(popup).to_have_url(target)
    expect(popup.locator("h1")).to_have_text("Bookmark destination")
    assert popup.evaluate("window.opener === null")
    assert popup.evaluate("document.referrer") == ""
    popup.close()
    assert len(context.pages) == 1


def choose_theme(page: Any, preset: str) -> None:
    page.locator("#themeBtn").click()
    page.locator("#themePreset").select_option(preset)
    page.locator("#applyTheme").click()
    expect(page.locator("#themeDialog")).not_to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-theme", preset)


def run_retro_card_scenarios(browser: Any, server: Any) -> list[str]:
    completed: list[str] = []
    with server(external=False) as base:
        target = base + "/destination?source=card#details"
        entries = [
            {"id": "retro", "title": "Retro terminal", "url": target,
             "description": "Documentation, reference material and classic computing.",
             "tags": ["computing/retro", "reference"]},
            {"id": "plain", "title": "Plain bookmark", "url": base + "/destination?plain=1",
             "description": "An untagged card.", "tags": []},
            {"id": "delete", "title": "Delete test", "url": base + "/destination?delete=1", "tags": []},
        ]
        external: list[str] = []
        visits: list[str] = []

        def route_request(route):
            url = route.request.url
            if url.startswith(base + "/destination"):
                visits.append(url)
                route.fulfill(content_type="text/html", body="<h1>Bookmark destination</h1>")
            elif url.startswith(base):
                route.continue_()
            else:
                external.append(url)
                route.abort()

        context = browser.new_context(viewport={"width": 1280, "height": 900})
        context.route("**/*", route_request)
        page = context.new_page()
        failures: list[str] = []
        page.on("pageerror", lambda error: failures.append(str(error)))
        assert page.request.post(base + "/api/import", data={"entries": entries}).ok
        page.goto(base)
        expect(page.locator(".card")).to_have_count(3)
        expect(page.locator("html")).to_have_attribute("data-theme", "gold-black")
        screenshots = os.getenv("KELLMARKS_FEATURE_SCREENSHOTS")
        for preset, phosphor in [("mono-green", "rgb(51, 255, 102)"), ("mono-amber", "rgb(255, 176, 0)")]:
            choose_theme(page, preset)
            page.reload()
            expect(page.locator("html")).to_have_attribute("data-theme", preset)
            assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(0, 0, 0)"
            assert page.evaluate("getComputedStyle(document.body).color") == phosphor
            assert "monospace" in page.evaluate("getComputedStyle(document.body).fontFamily")
            assert "monospace" in card(page, "Retro terminal").locator(".mini").first.evaluate("el => getComputedStyle(el).fontFamily")
            assert card(page, "Retro terminal").evaluate("el => getComputedStyle(el).color") == phosphor
            assert page.evaluate("getComputedStyle(document.body).textShadow") != "none"
            assert page.locator(".brand img").evaluate("el => getComputedStyle(el).filter") != "none"
            page.locator("#themeBtn").click()
            page.locator("#themePreset").select_option("forest")
            page.keyboard.press("Escape")
            expect(page.locator("html")).to_have_attribute("data-theme", preset)
            assert "monospace" in page.evaluate("getComputedStyle(document.body).fontFamily")
            if screenshots:
                page.screenshot(path=str(Path(screenshots) / f"kellmarks-{preset}.png"), full_page=True)
        for preset in ["forest", "mono", "custom", "gold-black"]:
            choose_theme(page, preset)
            assert "monospace" not in page.evaluate("getComputedStyle(document.body).fontFamily")
            assert page.evaluate("getComputedStyle(document.body).textShadow") == "none"
            assert page.locator(".brand img").evaluate("el => getComputedStyle(el).filter") == "none"
        assert external == [] and visits == []
        completed.append("green/amber monitor styling, reload persistence, cancel and clean restoration of other themes")

        # Verify coordinates, including areas outside the title's normal bounds.
        selected = card(page, "Retro terminal")
        selected.scroll_into_view_if_needed()
        points = [center(selected.locator(selector)) for selector in ["h3", ".icon", ".url", ".desc"]]
        box = selected.bounding_box()
        actions = selected.locator(".card-actions").bounding_box()
        edit = selected.get_by_role("button", name="Edit", exact=True).bounding_box()
        remove = selected.get_by_role("button", name="Delete", exact=True).bounding_box()
        chips = selected.locator(".chip").all()
        first = chips[0].bounding_box()
        second = chips[1].bounding_box()
        assert box and actions and edit and remove and first and second
        points.extend([
            (box["x"] + 8, box["y"] + 8),
            (box["x"] + box["width"] - 6, box["y"] + box["height"] / 2),
            (actions["x"] + 3, actions["y"] + actions["height"] / 2),
            ((edit["x"] + edit["width"] + remove["x"]) / 2, edit["y"] + edit["height"] / 2),
            ((first["x"] + first["width"] + second["x"]) / 2, first["y"] + first["height"] / 2),
        ])
        for point in points:
            assert page.evaluate("([x,y]) => document.elementFromPoint(x,y)?.closest('a')?.getAttribute('href')", point) == target
            opened_page(context, page, lambda point=point: page.mouse.click(*point), target)
        plain = card(page, "Plain bookmark")
        plain.scroll_into_view_if_needed()
        opened_page(context, page, lambda: page.mouse.click(*center(plain.locator(".desc"))), entries[1]["url"])
        completed.append("native links cover title, icon, URL, description, padding and button gaps on tagged/untagged cards")

        selected.scroll_into_view_if_needed()
        link = selected.get_by_role("link", name="Retro terminal", exact=True)
        expect(selected.locator("a")).to_have_count(1)
        expect(link).to_have_attribute("target", "_blank")
        expect(link).to_have_attribute("rel", "noopener noreferrer")
        link.focus()
        page.keyboard.press("Tab")
        expect(selected.locator(".chip").first).to_be_focused()
        page.keyboard.press("Shift+Tab")
        expect(link).to_be_focused()
        assert link.evaluate("el => getComputedStyle(el,'::after').outlineStyle") == "solid"
        opened_page(context, page, lambda: page.keyboard.press("Enter"), target)
        middle_point = point_over_link(page, selected.locator(".icon"), target)
        opened_page(context, page, lambda: page.mouse.click(*middle_point, button="middle"), target)
        modified_point = point_over_link(page, selected.locator(".desc"), target)
        page.keyboard.down("Control")
        try:
            opened_page(context, page, lambda: page.mouse.click(*modified_point), target)
        finally:
            page.keyboard.up("Control")
        completed.append("single link tab stop, whole-card focus, Enter, middle/modifier click and safe popup/referrer behavior")

        # Actions must work without any new navigation, including after rerender.
        before = len(visits)
        selected.get_by_role("button", name="Edit", exact=True).click()
        expect(page.locator("#editor")).to_be_visible()
        expect(page.locator("#title")).to_have_value("Retro terminal")
        page.locator("#desc").fill("Edited description")
        page.locator("#saveBtn").click()
        expect(page.locator("#editor")).not_to_be_visible()
        expect(selected.locator(".desc")).to_have_text("Edited description")
        selected.get_by_role("button", name="computing/retro", exact=True).click()
        expect(page.locator("#viewTitle")).to_have_text("computing/retro")
        expect(page.locator(".card")).to_have_count(1)
        page.locator("#tree").get_by_text("All", exact=True).click()
        expect(page.locator(".card")).to_have_count(3)
        deletion = card(page, "Delete test")
        page.once("dialog", lambda dialog: dialog.dismiss())
        deletion.get_by_role("button", name="Delete", exact=True).click()
        expect(deletion).to_be_visible()
        page.once("dialog", lambda dialog: dialog.accept())
        deletion.get_by_role("button", name="Delete", exact=True).click()
        expect(deletion).to_have_count(0)
        settle(page)
        assert len(visits) == before
        assert len(context.pages) == 1 and page.url == base + "/"
        selected.scroll_into_view_if_needed()
        opened_page(context, page, lambda: page.mouse.click(*center(selected.locator(".desc"))), target)
        assert failures == [] and external == []
        completed.append("Edit/save, tag filtering, Delete cancel/confirm remain isolated and card links survive rerender")
        context.close()

        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        context.route("**/*", route_request)
        page = context.new_page()
        page.goto(base)
        choose_theme(page, "mono-green")
        selected = card(page, "Retro terminal")
        selected.scroll_into_view_if_needed()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        touch_point = point_over_link(page, selected.locator(".icon"), target)
        opened_page(context, page, lambda: page.touchscreen.tap(*touch_point), target)
        selected.get_by_role("button", name="Edit", exact=True).tap()
        expect(page.locator("#editor")).to_be_visible()
        page.locator("#cancelBtn").tap()
        settle(page)
        assert len(context.pages) == 1
        if screenshots:
            selected.scroll_into_view_if_needed()
            page.screenshot(path=str(Path(screenshots) / "kellmarks-monitor-mobile.png"), full_page=True)
        assert external == []
        context.close()
        completed.append("mobile monitor layout and touch card navigation preserve independent button actions")
    return completed
