# KellMarks project roadmap

Roadmap revision: **01.01.00**
Approved scope: **2026-09-27**  
Baseline: **02.00.03**, application commit `de40dfa9ebecb6aa48d92c94d9e3b6e13cf40e01`, with community configuration at `b65cd0d71d201a90bc0df7ac1845a0745022cfcf`.  
Tracking issue: [#9](https://github.com/paulkakell/kellmarks/issues/9).

## Goal and boundaries

Make KellMarks a private bookmark library that is easy to save into, organize, search and recover. Retain the small Flask service, plain JavaScript dashboard, hierarchical tags, Boolean search and private atomic persistence. Every accepted recommendation is recorded below. A planned item is not an implemented feature. Historical release numbers below identify delivered work; remaining milestones have no assigned release number; they are not promised dates or published tags.

Multi-user collaboration, public sharing and mandatory AI are not part of this program. They require a separate product decision and security design. Existing local operation must remain useful without a browser extension, an AI model, external search, content preservation or an account with another service.

## Accepted feature register

| ID | Feature | Required scope | Delivery |
| --- | --- | --- | --- |
| KM-R01 | Safe imports and duplicates | Merge-default dashboard import; explicit replacement; JSON and browser bookmark HTML; folder-to-tag mapping; preview new, duplicate, changed and invalid entries; conservative URL comparison; retained originals; deliberate title/description choices and combined tags | 02.01.00 foundation; remaining work planned |
| KM-R02 | One-click capture | Authenticated quick-add page and bookmarklet first; browser extension; title and URL capture; optional selected text; existing-tag suggestions; already-saved feedback; Inbox destination | Planned; version unassigned |
| KM-R03 | Bulk library management | Multi-select; bulk tag addition/removal; tag rename, merge and move; optional descendant changes; previews; atomic operations; undo; later keyboard-accessible drag-and-drop | Planned; version unassigned |
| KM-R04 | Smart retrieval | Saved Boolean query, tag scope and sort order; dynamically evaluated collections; title/recently-added/recently-updated sorting; favorites; pinned collections; later domain, tag and date filters | 02.01.00 foundation; remaining work planned |
| KM-R05 | Recovery | Trash; configurable retention; immediate undo; recovery of bulk changes; accessible backup inventory and restore preview; per-bookmark history | Planned; version unassigned |
| KM-R06 | Explicit privacy controls | Library-only search by default; separate web-search action; visible external disclosure; remote-icon control; operator no-external-requests mode; policies for metadata, link checks, preservation and AI | Implemented controls |
| KM-R07 | Reading workflow | Inbox; unread/read; favorites; archive; optional review queue; clear separation between archive and Trash | Planned; version unassigned |
| KM-R08 | Notes and highlights | Longer notes; selected-text excerpts; source URL; capture timestamp; provenance; safe display; export and retrieval; revision recovery | Planned; version unassigned |
| KM-R09 | Link health and preservation | Manual and scheduled bounded checks; last-checked time; status taxonomy; redirect review; optional readable-text copies; later richer snapshots only when justified | Planned; version unassigned |
| KM-R10 | Mobile and offline | Mobile-friendly capture; installable application; explicit offline opt-in; persistent outbox; duplicate-resistant replay; conflict review; private cache lifecycle | Planned; version unassigned |
| KM-R11 | Optional local AI | Suggested tags, summaries, related bookmarks and semantic search; local processing first; explicit approval before edits; transparent model/index lifecycle; no AI requirement | Planned; version unassigned |

## Release sequence and acceptance criteria

### 02.01.00: safe import and privacy foundation

Status: implemented foundation in PR #10; release promotion requires the exact-commit validation gates below. Import-wide field choices ship first; per-item conflict editing remains a refinement.

Deliver a non-destructive import workflow, conservative duplicate review, explicit web search, remote-icon consent and useful sort controls. Keep data schema 2 and the existing CRUD/search/export contracts. The legacy API import request without a mode must continue to mean replacement; the dashboard selects merge explicitly. New guarded operations must detect library changes between preview and apply instead of overwriting concurrent edits.

Implement JSON/browser-HTML parsing without fetching imported URLs. Validate the complete candidate result before writing. Reject unsafe entries, duplicate IDs, ambiguous target collisions, tag-limit overflow and total-library overflow. Never silently strip arbitrary query parameters, equate HTTP and HTTPS, or erase URL fragments. Preserve existing identifiers and creation times when merging a known bookmark. Preserve the pre-import library in a private backup before committing a replacement or merge.

Examples: import another browser without deleting the current collection; preview a repeated reference page; search a confidential phrase locally without sending it to a search provider; sort recently added research first.

Acceptance: malformed imports make zero changes; cancel makes zero changes; stale previews return a conflict; a failed backup/write leaves the live store recoverable; existing API clients and schema-2 exports still work; local typing and dashboard rendering cause no unrequested external lookup; operator denial overrides browser preferences. Unit, API and browser-interaction tests must cover these properties.

### Planned: bulk organization and recovery

Dependencies: 02.01.00 validation, conflict detection and import preview conventions.

Add a selection model, selected-count display and previews for bulk tag addition/removal. Support renaming `work/aws` to `cloud/aws`, merging existing tag branches and moving descendants only with explicit scope. Count distinct affected bookmarks. Reject a move beneath its own descendant, invalid paths and over-limit results before committing.

Introduce Trash with a documented retention setting and immediate Undo. Add an operation journal sufficient to reverse bulk changes without undoing unrelated later edits. Undo must detect conflicts. Present backup timestamps, sizes, versions and restore previews; require an explicit destructive confirmation for full restore. Backups must stay private and have bounded retention.

Design persistence before implementation. Prefer a transactionally consistent single-store envelope; do not invent a multi-file pseudo-transaction. Write an architecture decision describing any schema extension, old-export import, forward validation and safe downgrade. A genuinely incompatible contract requires the next major version rather than pretending to be additive.

Examples: move an entire tag hierarchy; recover yesterday's accidental deletion while retaining today's additions; reverse a bulk tag operation without resetting the library.

Acceptance: multi-process writes remain serialized; all-or-nothing bulk mutations; Trash survives restart; retention boundary tests; backup corruption is rejected; restore is rehearsed against a disposable copy; no permanent deletion before its configured policy allows it. Drag-and-drop follows only after the same operations work by keyboard with visible previews.

### Planned: capture and reading

Dependencies: duplicate review and recovery.

Add an authenticated quick-add page that does not save on GET. A bookmarklet may transfer title, URL and optional selected text in a URL fragment, never a bearer token. Clear transferred data from browser history after reading it. Enforce ordinary authentication and require a user Save action. Do not accept arbitrary return URLs.

Add an extension using a user-triggered active-tab permission rather than broad browsing-history access. Request only permissions actually used. Store the configured KellMarks origin separately from credentials; document session expiration and revocation. Check duplicates before adding and show existing hierarchical tags. Capture selected text only after explicit user choice.

Add Inbox, unread/read, favorites, archive and an optional review queue. Archive is retained content, not Trash. Existing entries need a deterministic migration default, and every new field must round-trip through export/import. Saved captures remain recoverable when their source tab closes or the API request fails.

Examples: save an AWS article directly to `cloud/aws/security`; collect uncategorized reading in Inbox; mark it read later; archive completed reading without deleting it.

Acceptance: Chrome/Firefox compatibility matrix and installation instructions; no tokens in URLs, page DOM or logs; no passive capture; hostile page metadata displayed as text; retry never creates an unintended second bookmark; keyboard and mobile quick-add tests.

### Planned: smart retrieval and research context

Dependencies: reading fields and the recovery model.

Persist a smart collection as a name, validated Boolean query, tag scope and sort order, not a copied list of IDs. Evaluate it dynamically. Add collection editing, deleting and pinning. Add field-specific domain/tag/date filters with documented grammar shared by browser and server. Keep existing query meanings stable; invalid new syntax must give a useful error. Provide explicit empty-query semantics and timezone rules for date filters.

Expand short descriptions with separate notes and highlights. Preserve source URL and capture time on every excerpt; never present generated text as a verbatim source quotation. Support plain text first. Any Markdown support must exclude raw HTML and unsafe links. Add per-bookmark revision recovery and export of all research context.

Examples: save an AWS security collection using scope `cloud/aws` and query `iam OR "zero trust"`; pin it; find recently updated references; retain an excerpt explaining why an article mattered.

Acceptance: collection results update after CRUD/import; browser/server query parity fixtures; old Boolean queries remain unchanged; notes/highlights cannot execute scripts; export/import round-trips; revision restore preserves unrelated changes; a 10,000-entry retrieval benchmark with recorded environment and baseline.

### Planned: link health and optional preservation

Dependencies: central privacy policy, recoverable records and a reviewed outbound-request architecture.

Add manual checks before introducing schedules. Distinguish healthy, redirected, requires login, blocked, rate limited, timed out, missing and unknown. Record checked time and observed status. Never call a page gone merely because a bot challenge or authentication prevents retrieval. Redirect changes require review rather than silent URL replacement.

Use bounded, cancellable jobs with timeouts, response-size limits, concurrency caps, retry budgets and per-host pacing. Revalidate destinations on every redirect. Prevent access to loopback, private, link-local and metadata endpoints, including IPv6 and DNS-rebinding cases. Combine application validation with egress controls. Do not forward KellMarks credentials or website cookies.

Preservation begins with selected text or readable page text. Store content type, source, capture time and integrity hash. Render preserved content in a non-executable context and exclude remote resources. Enforce storage quotas, deletion and export. Do not bypass login, paywalls or access controls. Screenshots, PDFs and full HTML are later options subject to measured resource cost and a separate threat review.

Examples: review a moved documentation page; see that another page requires login rather than deleting it; retain a readable copy of a useful public reference.

Acceptance: SSRF regression corpus; simulated DNS changes and redirect chains; denied destinations never reached; global external denial cancels future work; job restart/retry idempotency; no sensitive URLs or text in logs; quota and retention tests; measured CPU, memory, storage and request budgets.

### Planned: mobile and deliberate offline support

Dependencies: stable capture, conflict detection and recovery.

Improve responsive navigation, target sizes, dialogs and keyboard/screen-reader behavior. Add an installable app shell. Offline storage is explicit opt-in; it is not an automatic fallback that silently creates a second authoritative library. Do not cache authenticated API responses or bearer tokens in a service-worker cache by default.

Persist an outbox of versioned operations with idempotency keys. Show pending, failed and conflicting operations. Reauthenticate before replay. Define conflicts for edits, deletes, restores and imports; allow review rather than last-writer-wins data loss. Keep local caches isolated by instance/account boundary and clear them on the documented logout/remove-device operation. Explain browser-storage limitations and the private data retained on the device.

Examples: save a reference while disconnected, see it pending, reconnect and confirm one server entry; resolve a title edited on two devices.

Acceptance: supported-browser install/offline matrix; interrupted writes and replay; duplicate suppression; expired-auth behavior; cross-instance isolation; cache removal; accessibility checks; offline import/export recovery; no claim of encrypted-at-rest storage without implementing and reviewing key management.

### Planned: optional local AI assistance

Dependencies: notes, retrieval, privacy policy and deletion/export lifecycle.

Add a provider interface with an operator-configured local endpoint, explicit model selection and bounded requests. Keep cloud processing disabled unless separately and explicitly enabled. Distinguish local model communication from external internet access in policy and documentation. Treat saved text as untrusted data, not instructions granting tools or filesystem access.

Offer suggested tags, draft summaries, related bookmarks and semantic search. Suggestions do not edit records until approved. Keep exact Boolean search available and label generated summaries. Store model/version provenance and define embedding/index rebuilds, retention, deletion and export behavior. Deleted private content must be removed from derived indexes.

Examples: suggest tags for Inbox items; approve only useful suggestions; locate a reference by meaning while retaining an exact-query alternative.

Acceptance: deterministic provider-mock tests; optional offline benchmark corpus with no personal data; model-unavailable fallback; timeout and size limits; prompt-injection fixtures; no auto-edit; deletion/index consistency; measured latency, memory and storage. Evaluate usefulness before making any model a default.

## Architecture and engineering rules

Keep server validation authoritative. Extract pure import and library-operation helpers as their complexity grows; avoid a framework rewrite or microservices as prerequisites. Use one documented canonical URL identity rule for duplicate comparison and retain original URLs. Do not normalize away query strings, fragments or meaningful path distinctions.

Preserve atomic writes, cross-process locking, private file permissions, explicit limits, trusted-host checks, bearer authentication, exact-origin CORS and structured request IDs. New API routes must pass the same authentication, rate-limit and error-handling gates. A no-external-requests policy must cover every application-owned outbound path, not merely hide a button. Normal user navigation to a bookmarked website is a separate explicit browser action.

Client-only preferences must be labeled as device-local until synchronized persistence exists. Never claim that the existing browser fallback is synchronization. Introduce worker queues, search indexes or a database only when an implemented feature has demonstrated the need; document migration and rollback first.

## Required release evidence

Every implementation release must complete these gates, with actual output rather than a checked box based on intention:

1. Increment `xx.xx.xx`: major for incompatible contracts, feature for compatible additions, patch for fixes. Align VERSION, API/UI constants, README, OpenAPI, notes, smoke checks and the immutable release tag. Preserve historical release documents.
2. Record what changed, why and whether it is additive, breaking or a fix. Reference #9, actual PRs and actual commit hashes; never invent future hashes.
3. Run all existing and new unit, integration and regression tests. Add browser-interaction tests for UI behavior, not only source-text assertions.
4. Run compilation, JavaScript syntax validation, Ruff, mypy, Bandit, secret scanning and CodeQL. Resolve structural/security findings.
5. Review authentication, authorization, validation, logging, secrets and outbound requests. Audit pinned dependencies; regenerate locks only when needed.
6. Validate installation and startup in clean Python 3.10 and 3.13 environments. Keep source and validation artifacts tied to the exact commit and version; exclude runtime data and credentials.
7. Verify defaults, environment variables, feature flags and malformed-configuration behavior. Document all new options with examples.
8. Review schema changes, old-data import, forward compatibility and rollback. Rehearse migrations and restore against disposable copies before release.
9. Benchmark changed core logic and I/O at realistic sizes, including 10,000 entries. Record the environment and do not label unmeasured targets as results.
10. Verify structured logs and request IDs; do not log tokens, bookmark contents or query strings. Add only non-sensitive counters/metrics with documented meaning.
11. Update README, API/OpenAPI, architecture documentation and user guides. Cover every feature and option with an example and a failure/recovery case.
12. Review API/CLI/config/export compatibility explicitly. Define a rollback path and retain prior source/tag artifacts.
13. Attach release notes, validation evidence and copyable commit notes. Publish a tag only after the required checks pass for that exact commit.

## Delivery ledger

| Release | Status | Evidence |
| --- | --- | --- |
| 02.00.03 baseline | Existing application baseline | `de40dfa9ebecb6aa48d92c94d9e3b6e13cf40e01` |
| Roadmap 01.00.00 | Accepted scope recorded | #9; preparation commit `c3355bf6c4079c408f2cee5d7d116f1da0b3bfad` |
| 02.01.00 | Import/privacy/sorting foundation implemented; release gates apply | PR #10; [release notes](releases/02.01.00.md) and [user guide](USER_GUIDE.md) |
| 02.01.01 / 02.01.02 | Dashboard defaults, themes, version status and card navigation | [02.01.01](releases/02.01.01.md), [02.01.02](releases/02.01.02.md) |
| 02.02.00 | Docker/GHCR deployment, not bulk organization | PR #14, #16; [release notes](releases/02.02.00.md) |
| 02.02.01 | Release-download correction merged | PR #17; main `66a4c2a143bb7c6eaaaa67c7fddbec51a4919ada`; publication has separate exact-commit gates |
| 02.03.00 | Settings and opt-in blank-description implementation | PR #15; [release notes](releases/02.03.00.md); not the capture/reading milestone |
| Remaining accepted milestones | Planned; release numbers unassigned | Acceptance criteria above; no completion claim |

## References

Security design references, consulted 2026-09-27: [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) and [Chrome user-triggered activeTab permission](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab). These inform later implementation; they do not establish that an unimplemented control already exists.


## Dashboard follow-up — 02.01.01

The September 27, 2026 follow-up implements four separately requested dashboard changes: consent-controlled site favicon fallback, local creation-only site tags, 20 theme presets/custom colors with gold/black as default, and cached release status in the footer. These changes do not imply completion of local AI (KM-R11), bulk editing, capture or any other remaining milestone above. The tag suggestions are deterministic local rules and reuse, not an AI implementation. See `releases/02.01.01.md` for behavior, privacy limits and rollback.

## September 27 integration status

The originally proposed 02.02.00–02.07.00 milestone numbers were planning targets,
not reserved release tags. Intervening Docker/GHCR and Settings/description work
uses 02.02.00–02.03.00. The remaining milestone sequence and acceptance criteria
are retained without conflicting version promises. Issue #9 stays open until
that work is implemented and validated. Session-only description metadata is a
limited addition, not a browser extension, notes/highlights system, link-health
scanner, readable-text preservation service or AI summarizer.
