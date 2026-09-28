# KellMarks user guide 02.01.02

This guide describes implemented behavior. The [roadmap](ROADMAP.md) describes later work and should not be read as a current feature list.

## Settings

Open **Settings** in the header for **Theme**, **Import links (JSON / HTML)**, **Export links (JSON)**, **Allow remote icons for this session**, and **Clear browser memory…**. Import/export no longer appear in the hierarchy sidebar. The installed version and update check appear only in the footer, not beside the logo.

Settings works with mouse, touch or keyboard. Tab moves between its native controls; Escape, the Settings button, or a click outside dismisses it. Theme and import dialogs retain their preview/cancel behavior and return focus to their Settings control when closed. Remote icons still require session consent and the operator's permission. JSON exports include the full library, regardless of the current search or tag filter. Reviewed imports still require an available server; static/browser-only collections can be exported.

### Clear browser memory

**Settings → Clear browser memory…** opens a confirmation with **Cancel** focused. Nothing is removed until **Clear and reload** is selected. Export browser-only links first: deletion cannot be undone.

The action removes Kellmarks-owned local and session storage for this origin, including browser-only bookmarks, the saved theme, and this tab's API token. It reloads the page, restoring the default theme, resetting search/sort and remote-icon consent, and asking for authentication again when required. Server bookmarks, private backups and downloaded exports are not deleted. A static host may show its bundled sample bookmarks again after the local copy is removed.

Other applications' keys on the same origin, cookies, the browser's HTTP cache, and other sites are not cleared. Other open tabs keep their in-memory state and session tokens; close or reload them separately to avoid retaining or re-saving stale data. If browser policy blocks clearing storage, an error is shown without automatically reloading or claiming success; accessible data may already have been removed. Correct the browser's site-data permissions and retry.

## Bring in an existing collection

Start the Flask service and open KellMarks. Select **Settings → Import links (JSON / HTML)**, then choose a KellMarks JSON export, a JSON array of bookmark objects, or a browser bookmark export ending in `.html` or `.htm`. The first preview defaults to **Merge with my library**. Nothing is saved during preview.

For example, import a second browser's bookmarks while keeping everything already organized in KellMarks. The preview reports new entries, matching URLs, existing bookmarks that would change, unchanged matches and the final library size. The detail pane shows the first 100 items; the summary counts the complete import.

Choose **Apply import** only after reviewing the result. A private pre-import `.bak` is created before the atomic save. Successful apply reloads the dashboard. Cancel, Escape or Close discards the preview without changing the library. Closing is temporarily disabled while an apply request is in progress, to avoid suggesting that an already-sent write was cancelled.

### Duplicate choices

For matching URLs, tags are combined case-insensitively. The existing saved URL, ID, creation timestamp and icon remain unchanged. **Keep existing title** and **Keep existing description** are the defaults. Selecting **Use incoming title** or **Use nonempty incoming description** changes those fields for every matching bookmark in this import. An empty imported description does not erase an existing description. Change either option, then select **Preview** again before applying.

Example: import a duplicate reference with tag `research/aws`. Keep its carefully edited existing title, but choose the incoming nonempty description. Its old tags and new tag are retained. This release has import-wide choices, not a separate editor for each conflict; edit the source file or bookmarks for per-item decisions. Richer conflict editing remains in the roadmap.

URLs are compared conservatively. Hostname case, explicit default ports and an omitted root slash compare equally. HTTP and HTTPS, different query values, different fragments, path case and non-root trailing slashes remain distinct. Arbitrary tracking or query parameters are not stripped. Existing URL text is retained even when a normalized identity matched it.

If an incoming URL matches multiple existing bookmarks, the merge is blocked. Review those existing entries individually first. An incoming ID associated with a different URL is also blocked; remove that ID from the import object so preview can assign a new one, or correct the URL. Invalid entries, duplicate IDs inside the file, over-limit merged tags and oversized resulting libraries do not cause a partial import.

### Browser HTML

KellMarks reads bookmark HTML as text without opening saved URLs or loading images, scripts or other embedded resources. Browser folder names become hierarchical tags. For example, folders `Work` then `AWS` produce `Work/AWS`. Literal slashes and percent signs inside folder names are represented as `%2F` and `%25`, so a folder name cannot accidentally create a different hierarchy. A folder depth above 32 or tag path above the normal 80-character limit is rejected.

Titles, URLs and supported description text are imported. Browser-specific metadata, favicon blobs, browser timestamps and empty folders are not preserved in this first importer. Created/updated timestamps for HTML entries are assigned during preview. KellMarks JSON exports preserve their valid IDs and timestamps for new entries.

### Replace everything deliberately

Select **Replace my entire library**, preview again, then review the number of existing and incoming bookmarks. Apply requires a second confirmation. A JSON file with an empty entries array can intentionally clear the library in this mode. Merging an empty array does not delete existing entries.

Example: restore a previously saved complete export. First export the current library to a separate file, then preview and confirm replacement. Do not treat the rolling `.bak` as a multi-version history.

### Limits and failures

The dashboard accepts files up to 1 MiB and at most 5,000 imported entries. The default server request limit is also 1 MiB, including the JSON envelope, so a file near the maximum can still exceed the request limit after serialization. The default resulting-library limits are 10,000 entries and 16 MiB. Each bookmark allows 32 tags, 80 characters per tag, a 120-character title, 600-character description and 2,048-character URL. Operator-configured limits may be stricter; the server is authoritative. No browser truncation silently turns invalid import data into accepted data.

A preview returns up to 50 entry errors and the complete invalid count. Correct the source file and select it again. A stale preview means another edit occurred after review; preview again and inspect the new result. A failed or uncertain request requires a fresh preview before retrying. If the UI says the import was saved but reload failed, reload the page rather than repeating replacement. The atomic-write and backup protections do not replace independent backups or disk monitoring.

Reviewed import requires an available Flask API. It is unavailable in file/static/browser-only fallback mode. Existing browser-local entries can still be exported and later imported into the server. This is not synchronization; the fallback and server stores remain separate.

## Search privately and choose external requests

Typing in **Search my library**, switching tags, sorting, editing or importing does not send the library query to a search provider. Use the existing Boolean grammar, for example `iam OR "zero trust"` under tag `cloud/aws`.

**Search the web** explicitly sends the current query to DuckDuckGo through the server proxy. It is enabled only for a nonempty query of at most 256 characters when the server allows external requests. A new query cancels and hides stale external results. External responses are not automatically saved as bookmarks. Direct API clients can still request the proxy when the operator permits it.

Remote bookmark icons are off on every page load. Selecting **Settings → Allow remote icons for this session** contacts the websites named by saved icon URLs. The choice is held in page memory, not persisted to disk, and resets on reload. Unchecking stops future image loads, but cannot retract requests already sent. Initial-letter placeholders remain available without external requests.

For an operator-enforced policy, set:

```bash
export KELLMARKS_EXTERNAL_REQUESTS=0
python docs/server/app.py
```

The server refuses the DDG endpoint before a network call and removes remote image sources from the response Content Security Policy. Dashboard controls are disabled. The default `1` preserves the direct API contract but does not enable automatic dashboard searches or icons. Valid boolean forms are `1/0`, `true/false`, `yes/no` and `on/off`, case-insensitive. Invalid values stop startup. Restart and reload open pages after changing it.

This setting controls application-owned lookups, not all machine traffic. Clicking a saved website or an external documentation link remains explicit browser navigation. No metadata fetcher, link checker, preservation worker or AI provider is implemented yet; each must obey the policy when introduced.

## Sort the current view

Choose **Title**, **Recently added** or **Recently updated**. Sorting applies within the current query and tag scope. Dates sort newest first; equal values use title and then ID for stable ordering. The choice resets on page reload and is not yet a saved smart collection.

Example: filter `cloud/aws`, search `security`, then choose **Recently added** to review the newest matching bookmarks. Sorting never triggers a web search.

## Recovery and rollback

Before an import, save an independent export. After a successful import, the previous file is at the configured data path plus `.bak`, by default `docs/server/instance/data.json.bak`. It is private and not available through static web routes. Copy it to a separate location before another import overwrites it. Select that copy as a JSON import, choose replacement, and review before restoring. Stop other writers while performing an operator-level file restore.

Schema 2 is unchanged, so a 02.01.00 export is compatible with the prior 02.00.03 importer. Keep the previous code artifact and a private data copy before downgrading. Detailed operator steps are in [release notes](releases/02.01.00.md).

There is no Trash, per-bookmark undo/history, backup browser, bulk tag editor, capture extension, read-later status, saved collection, offline sync or AI feature in this release. Those accepted features have explicit delivery milestones in the roadmap.


## Entry defaults and appearance (02.01.01)

Leave **Icon URL** blank to try the site's HTTPS `/favicon.ico`. This is a display fallback: an automatically chosen favicon is not written into the entry, so changing a bookmark URL uses the new site's icon. An explicit icon URL takes priority. Check **Settings → Allow remote icons for this session** to permit these website requests; an unavailable icon shows initials. No third-party icon service is used. The operator's external-request deny switch still wins.

Leave **Tags** blank when adding an entry to use up to five local suggestions. Kellmarks first reuses common tags for that same hostname, then uses bundled site rules, then falls back to `sites/<hostname>`. These are deterministic local suggestions, not fetched site keywords or AI output. Manual tags are retained. Editing a bookmark never regenerates tags: clearing them keeps it untagged, including after a URL change or reload. Imported and existing records are not backfilled.

Select **Settings → Theme** for 22 presets or five custom colors: page background/text, accent, and card background/text. Preview is immediate. **Apply theme** saves to this browser, **Cancel** or Escape restores the previous selection, and **Gold / black** previews the original default. Low-contrast custom combinations produce a warning rather than silently overriding your choices. Theme settings do not change the shared bookmark file or other browsers. When browser storage is blocked, a theme can still be applied for the current page.

### Monochrome monitors and card navigation (02.01.02)

Choose **Monochrome green (1980s)** or **Monochrome amber (1980s)** for phosphor-colored text on black, dark cards with matching borders, a monospace typeface and a subtle static glow. Logos and allowed remote icons are tinted to match. These presets add no animation, flicker, fonts or network requests. All 20 existing presets, custom colors and saved preferences remain available; gold/black is still the default. Switching to another preset or custom colors removes the monitor-specific styling.

Click the title, icon, URL, description, card padding or the gaps between controls to open the bookmark in a new tab, matching the existing title-link behavior. **Edit**, **Delete** and tag buttons do not open the bookmark; they keep their editor, confirmation and filtering actions. The card uses a native link with one keyboard tab stop: press **Enter** to open it. Middle-click, modifier-click and the browser's link context menu also work. Keyboard focus outlines the entire card; buttons have their own focus outline.

## Installed version and updates (02.01.01)

The bottom of the page displays the installed version, release status, a **Check again** button and the latest-release link. With the API available, the server automatically checks public GitHub release metadata. It sends no bookmark content or API credentials. The status distinguishes **Up to date**, **Update available**, a development build ahead of the release, no published stable release, unavailable and operator-disabled.

Results are cached per server process for one hour, or five minutes after an unsuccessful check. **Check again** refreshes the displayed cached result and retries upstream once the cache expires; the timestamp identifies the actual network attempt. A network error never means the software is current. The check does not download or install updates.

`KELLMARKS_EXTERNAL_REQUESTS=0` disables the lookup. Static demonstration mode shows a manual release link and explains that automatic checking requires the server. Creation-time tag suggestions and themes still work locally when external requests are disabled or the API is unavailable.
