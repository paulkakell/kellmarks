"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const vm = require("node:vm");
const context = vm.createContext({ URL, console });
vm.runInContext(fs.readFileSync("docs/assets/enhancements.js", "utf8"), context);
const f = context.KellmarksEnhancements;
const plain = (value) => JSON.parse(JSON.stringify(value));
const rules = JSON.parse(fs.readFileSync("docs/assets/site-tags.json", "utf8"));

test("favicon uses HTTPS origin only, supports IPv6, and rejects unsafe URLs", () => {
  assert.equal(f.faviconURL("https://example.test/private?token=secret#part"), "https://example.test/favicon.ico");
  assert.equal(f.faviconURL("http://example.test/path"), "https://example.test/favicon.ico");
  assert.equal(f.faviconURL("http://[::1]:8787/path"), "https://[::1]:8787/favicon.ico");
  for (const value of ["", "javascript:alert(1)", "data:image/png,abc", "https://user:pass@example.test/"]) {
    assert.equal(f.faviconURL(value), "");
  }
});

test("site suggestions match the server rules without network lookups", () => {
  for (const [url, expected] of [
    ["https://github.com/org/repo", ["development/git", "software/open-source"]],
    ["https://docs.python.org/3/", ["development/python"]],
    ["https://github.com.evil.test/path", ["sites/github.com.evil.test"]],
    ["https://notgithub.com/", ["sites/notgithub.com"]],
    ["http://www.EXAMPLE.test.:8080/a?q=private#secret", ["sites/example.test"]],
    ["https://bücher.example/", ["sites/xn--bcher-kva.example"]],
    ["http://[::1]:8787/", ["sites/::1"]]
  ]) assert.deepEqual(plain(f.suggestTags(url, [], rules)), expected);
  assert.deepEqual(plain(f.suggestTags("", [], rules)), []);
  assert.deepEqual(plain(f.suggestTags("https://unknown.test/", [], {})), ["sites/unknown.test"]);
});

test("existing tags take precedence with deterministic frequency, deduplication and bounds", () => {
  const entries = [
    { url: "https://www.github.com/first", tags: ["Team", "a", "b", "c", "d", "e"] },
    { url: "https://github.com/second", tags: ["team"] },
    { url: "https://github.com.evil.test/", tags: ["not-related"] }
  ];
  assert.deepEqual(plain(f.suggestTags("https://github.com/third", entries, rules)), ["Team", "a", "b", "c", "d"]);
});

test("there are exactly 20 unique readable presets and gold/black remains default", () => {
  assert.equal(f.THEMES.length, 20);
  assert.equal(new Set(f.THEMES.map((theme) => theme.id)).size, 20);
  assert.equal(f.THEMES[0].id, "gold-black");
  assert.deepEqual(plain(f.THEMES[0].colors), { bg: "#000000", fg: "#FFFFFF", accent: "#FFD700", card: "#FFD700", cardText: "#000000" });
  for (const theme of f.THEMES) {
    assert.ok(f.contrast(theme.colors.bg, theme.colors.fg) >= 4.5, theme.id);
    assert.ok(f.contrast(theme.colors.card, theme.colors.cardText) >= 4.5, theme.id);
  }
});

test("theme preferences strictly validate and discard CSS injection and corrupt data", () => {
  for (const data of [null, {}, [], {version: 2}, {version: 1, preset: "not-a-preset"}, {version: 1, preset: "custom", colors: {bg:"url(https://evil.test)"}}]) {
    assert.equal(f.normalizeTheme(data).preset, "gold-black");
  }
  const colors = {bg:"#112233",fg:"#ffffff",accent:"#aabbcc",card:"#222222",cardText:"#ffffff"};
  const theme = f.normalizeTheme({version:1, preset:"custom", colors});
  assert.equal(theme.preset, "custom");
  assert.equal(theme.colors.accent, "#AABBCC");
  assert.equal(f.normalizeTheme({version:1,preset:"forest",colors:{}}).colors.bg, "#0D2118");
});

test("missing or invalid rule assets degrade to a local hostname fallback", async () => {
  context.fetch = async () => { throw new Error("offline"); };
  assert.deepEqual(plain(await f.loadSiteRules()), {});
  context.fetch = async () => ({ok:false});
  assert.deepEqual(plain(await f.loadSiteRules()), {});
  context.fetch = async () => ({ok:true,json:async () => []});
  assert.deepEqual(plain(await f.loadSiteRules()), {});
  context.fetch = async () => ({ok:true,json:async () => ({"good.test":["work"],"bad.test":["x".repeat(81)]})});
  assert.deepEqual(plain(await f.loadSiteRules()), {"good.test":["work"]});
});
