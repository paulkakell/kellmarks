(() => {
  "use strict";

  const THEME_KEY = "kellmarks_theme_v1";
  const RELEASE_PAGE = "https://github.com/paulkakell/kellmarks/releases/latest";
  const COLOR_KEYS = ["bg", "fg", "accent", "card", "cardText"];
  const COLOR_IDS = ["themeBackground", "themeText", "themeAccent", "themeCard", "themeCardText"];
  const palettes = [
    ["gold-black", "Gold / black (default)", "#000000", "#FFFFFF", "#FFD700", "#FFD700", "#000000"],
    ["ocean", "Ocean", "#081C2C", "#F0F8FF", "#67D4FF", "#9FE4FF", "#082030"],
    ["forest", "Forest", "#0D2118", "#F0FFF4", "#77D9A0", "#ADEAC1", "#102A1B"],
    ["violet", "Violet", "#191027", "#FAF5FF", "#C4A1FF", "#DCC7FF", "#29143F"],
    ["ruby", "Ruby", "#270F17", "#FFF4F6", "#FF8AA5", "#FFB4C6", "#3A1121"],
    ["amber", "Amber", "#231A0B", "#FFF8EA", "#FFBE55", "#FFD393", "#312009"],
    ["teal", "Teal", "#082525", "#EDFFFF", "#60DED0", "#9AEDE3", "#08332E"],
    ["cobalt", "Cobalt", "#101B36", "#F1F5FF", "#8CAEFF", "#BBD0FF", "#15274C"],
    ["rose", "Rose", "#281323", "#FFF3FC", "#EFA1D5", "#F7C8E8", "#38182E"],
    ["lime", "Lime", "#18200D", "#F7FFE9", "#BDE66B", "#D7F3A2", "#26340F"],
    ["copper", "Copper", "#251912", "#FFF6F0", "#EFAE7D", "#F3CBAC", "#382317"],
    ["slate", "Slate", "#17212B", "#F3F6FA", "#B6CADC", "#D3E0EC", "#233344"],
    ["midnight", "Midnight", "#080B16", "#F2F4FF", "#A6B3FF", "#242D50", "#F2F4FF"],
    ["arctic", "Arctic", "#EDF5FA", "#17324A", "#145E88", "#FFFFFF", "#17324A"],
    ["paper", "Paper", "#F6F2E9", "#342A1C", "#73531D", "#FFFCF5", "#342A1C"],
    ["sand", "Sand", "#F4E9DA", "#3E2B19", "#895010", "#FFF7EB", "#3E2B19"],
    ["lavender", "Lavender", "#F2EDFA", "#322349", "#70429A", "#FEFAFF", "#322349"],
    ["mint", "Mint", "#EAF6EF", "#1B3C2A", "#216B44", "#F7FFFA", "#1B3C2A"],
    ["peach", "Peach", "#FFF0E7", "#4A2B20", "#924424", "#FFF9F4", "#4A2B20"],
    ["mono", "Monochrome", "#171717", "#F5F5F5", "#FFFFFF", "#E5E5E5", "#171717"],
    ["mono-green", "Monochrome green (1980s)", "#000000", "#33FF66", "#33FF66", "#001408", "#33FF66"],
    ["mono-amber", "Monochrome amber (1980s)", "#000000", "#FFB000", "#FFB000", "#1A1000", "#FFB000"]
  ];
  const THEMES = palettes.map(([id, name, ...values]) => Object.freeze({
    id, name, colors: Object.freeze(Object.fromEntries(COLOR_KEYS.map((key, i) => [key, values[i]])))
  }));

  function siteHost(value) {
    try {
      const url = new URL(value);
      if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return "";
      return url.hostname.toLowerCase().replace(/^\[|\]$/g, "").replace(/\.+$/, "").replace(/^www\./, "");
    } catch (_error) {
      return "";
    }
  }

  function faviconURL(value) {
    if (!siteHost(value)) return "";
    const url = new URL(value);
    // Only the origin is used, never a bookmark's private path, query, or fragment.
    // HTTPS also keeps HTTP bookmarks compatible with the existing image policy.
    url.protocol = "https:";
    url.pathname = "/favicon.ico";
    url.search = "";
    url.hash = "";
    return url.href;
  }

  function suggestTags(url, entries, rules = {}) {
    const host = siteHost(url);
    if (!host) return [];
    const counts = new Map();
    const labels = new Map();
    for (const entry of entries) {
      if (siteHost(entry.url) !== host) continue;
      for (const tag of entry.tags || []) {
        if (!tag) continue;
        const key = tag.toLowerCase();
        counts.set(key, (counts.get(key) || 0) + 1);
        if (!labels.has(key)) labels.set(key, tag);
      }
    }
    const alphabetical = (a, b) => a < b ? -1 : a > b ? 1 : 0;
    if (counts.size) {
      return [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a) || alphabetical(a, b))
        .slice(0, 5).map((key) => labels.get(key));
    }
    const domains = Object.keys(rules).sort((a, b) => b.length - a.length || alphabetical(a, b));
    for (const domain of domains) {
      if (host === domain || host.endsWith(`.${domain}`)) return rules[domain].slice(0, 5);
    }
    return [`sites/${host.slice(0, 74)}`];
  }

  async function loadSiteRules() {
    try {
      const response = await fetch("assets/site-tags.json", { cache: "force-cache" });
      if (!response.ok) return {};
      const rules = await response.json();
      if (!rules || typeof rules !== "object" || Array.isArray(rules)) return {};
      return Object.fromEntries(Object.entries(rules).filter(([domain, tags]) => (
        /^[a-z0-9.-]+$/.test(domain) && Array.isArray(tags) && tags.length > 0 &&
        tags.every((tag) => typeof tag === "string" && tag.length > 0 && tag.length <= 80)
      )));
    } catch (_error) {
      return {};
    }
  }

  function normalizeTheme(value) {
    if (value?.version !== 1) return { version: 1, preset: THEMES[0].id, colors: { ...THEMES[0].colors } };
    const preset = THEMES.find((theme) => theme.id === value.preset);
    if (preset) return { version: 1, preset: preset.id, colors: { ...preset.colors } };
    if (value.preset === "custom" && COLOR_KEYS.every((key) => /^#[0-9a-f]{6}$/i.test(value.colors?.[key]))) {
      return { version: 1, preset: "custom", colors: Object.fromEntries(COLOR_KEYS.map((key) => [key, value.colors[key].toUpperCase()])) };
    }
    return normalizeTheme(null);
  }

  function rgb(hex) {
    return [1, 3, 5].map((start) => Number.parseInt(hex.slice(start, start + 2), 16));
  }

  function luminance(hex) {
    const values = rgb(hex).map((channel) => {
      const value = channel / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722;
  }

  function contrast(a, b) {
    const values = [luminance(a), luminance(b)];
    return (Math.max(...values) + 0.05) / (Math.min(...values) + 0.05);
  }

  function applyTheme(value) {
    const theme = normalizeTheme(value);
    const colors = theme.colors;
    const root = document.documentElement;
    const variables = { bg: "bg", fg: "fg", accent: "accent", card: "card-bg", cardText: "card-fg" };
    for (const key of COLOR_KEYS) {
      root.style.setProperty(`--${variables[key]}`, colors[key]);
      root.style.setProperty(`--${variables[key]}-rgb`, rgb(colors[key]).join(","));
    }
    root.style.setProperty("--card-tint-rgb", luminance(colors.cardText) > 0.5 ? "0,0,0" : "255,255,255");
    const bg = rgb(colors.bg);
    const fg = rgb(colors.fg);
    root.style.setProperty("--control-bg", `rgb(${bg.map((v, i) => Math.round(v * 0.91 + fg[i] * 0.09)).join(",")})`);
    root.style.colorScheme = luminance(colors.bg) > 0.5 ? "light" : "dark";
    root.dataset.theme = theme.preset;
  }

  function setupThemes() {
    const $ = (selector) => document.querySelector(selector);
    let saved = normalizeTheme(null);
    try {
      saved = normalizeTheme(JSON.parse(localStorage.getItem(THEME_KEY)));
    } catch (_error) {
      // Blocked storage or a damaged preference must not stop the dashboard.
    }
    applyTheme(saved);
    const dialog = $("#themeDialog");
    const select = $("#themePreset");
    const inputs = COLOR_IDS.map((id) => $(`#${id}`));
    let draft = saved;
    for (const theme of THEMES) {
      select.add(new Option(theme.name, theme.id));
    }
    select.add(new Option("Custom colors", "custom"));

    function preview() {
      applyTheme(draft);
      select.value = draft.preset;
      inputs.forEach((input, index) => {
        input.value = draft.colors[COLOR_KEYS[index]];
        $(`#${input.id}Hex`).textContent = input.value.toUpperCase();
      });
      const textRatio = contrast(draft.colors.bg, draft.colors.fg);
      const cardRatio = contrast(draft.colors.card, draft.colors.cardText);
      const warning = textRatio < 4.5 || cardRatio < 4.5;
      $("#themeContrast").textContent = `${warning ? "Low text contrast. " : ""}Page ${textRatio.toFixed(1)}:1 · cards ${cardRatio.toFixed(1)}:1. Aim for at least 4.5:1.`;
      $("#themeContrast").dataset.warning = String(warning);
    }

    function cancel() {
      applyTheme(saved);
      dialog.close();
    }

    $("#themeBtn").addEventListener("click", () => {
      draft = normalizeTheme(saved);
      preview();
      dialog.showModal();
    });
    select.addEventListener("change", () => {
      draft = normalizeTheme({ version: 1, preset: select.value, colors: draft.colors });
      preview();
    });
    inputs.forEach((input) => input.addEventListener("input", () => {
      draft = normalizeTheme({ version: 1, preset: "custom", colors: Object.fromEntries(inputs.map((element, i) => [COLOR_KEYS[i], element.value])) });
      preview();
    }));
    $("#resetTheme").addEventListener("click", () => {
      draft = normalizeTheme(null);
      preview();
    });
    $("#themeForm").addEventListener("submit", (event) => {
      event.preventDefault();
      saved = normalizeTheme(draft);
      applyTheme(saved);
      try {
        localStorage.setItem(THEME_KEY, JSON.stringify(saved));
        dialog.close();
      } catch (_error) {
        $("#themeContrast").textContent = "Theme applied for this page. Browser storage is unavailable, so it cannot be saved across reloads.";
      }
    });
    $("#cancelTheme").addEventListener("click", cancel);
    $("#closeTheme").addEventListener("click", cancel);
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); cancel(); });
  }

  function setupVersionCheck({ apiReady, externalRequestsAllowed, apiFetch, version }) {
    const current = document.querySelector("#versionCurrent");
    const status = document.querySelector("#versionStatus");
    const checked = document.querySelector("#versionChecked");
    const button = document.querySelector("#checkVersion");
    const link = document.querySelector("#releaseLink");
    current.textContent = `Kellmarks v${version}`;
    link.href = RELEASE_PAGE;
    if (!apiReady || !externalRequestsAllowed) {
      status.textContent = !apiReady ? "Automatic update check requires the server" : "Update checks disabled by operator";
      button.disabled = true;
      return;
    }
    let running = false;
    async function check() {
      if (running) return;
      running = true;
      button.disabled = true;
      status.textContent = "Checking for updates…";
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 6500);
      try {
        const result = await apiFetch("/api/version", { signal: controller.signal });
        const messages = {
          current: "Up to date",
          update_available: `Update available: v${result.latestVersion}`,
          ahead: "Development build — ahead of latest release",
          unavailable: "Update check unavailable",
          no_release: "No published stable release found",
          disabled: "Update checks disabled by operator"
        };
        const versionPattern = /^v?[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}$/i;
        if (!Object.hasOwn(messages, result.status) || !versionPattern.test(result.currentVersion) ||
            (["current", "update_available", "ahead"].includes(result.status) && !versionPattern.test(result.latestVersion))) {
          throw new Error("Invalid version response");
        }
        current.textContent = `Kellmarks v${result.currentVersion}`;
        status.textContent = messages[result.status];
        const date = new Date(result.checkedAt || "");
        checked.textContent = Number.isNaN(date.getTime()) ? "" : `Last checked ${date.toLocaleString()}`;
      } catch (_error) {
        status.textContent = "Update check unavailable";
        checked.textContent = "";
      } finally {
        window.clearTimeout(timeout);
        running = false;
        button.disabled = false;
      }
    }
    button.addEventListener("click", check);
    void check();
  }

  // Limit the reset to this application's namespace; never clear another app's
  // data on a shared origin. Access can throw even before a Storage method runs.
  function clearBrowserMemory(scope = globalThis) {
    const failed = [];
    for (const area of ["localStorage", "sessionStorage"]) {
      let storage;
      let keys;
      try {
        storage = scope[area];
        keys = Array.from({ length: storage.length }, (_, index) => storage.key(index))
          .filter((key) => typeof key === "string" && key.startsWith("kellmarks_"));
      } catch (_error) {
        failed.push(area);
        continue;
      }
      for (const key of keys) {
        try {
          storage.removeItem(key);
          if (storage.getItem(key) !== null) throw new Error("Storage removal failed");
        } catch (_error) {
          if (!failed.includes(area)) failed.push(area);
        }
      }
    }
    return failed;
  }

  function setupSettings() {
    const $ = (selector) => document.querySelector(selector);
    const control = $(".settings-control");
    const button = $("#settingsBtn");
    const menu = $("#settingsMenu");
    const dialog = $("#clearMemoryDialog");
    const status = $("#clearMemoryStatus");

    function positionMenu() {
      if (menu.hidden) return;
      menu.style.transform = "none";
      const bounds = menu.getBoundingClientRect();
      const shift = bounds.left < 16 ? 16 - bounds.left
        : Math.min(0, window.innerWidth - 16 - bounds.right);
      menu.style.transform = `translateX(${shift}px)`;
      menu.style.maxHeight = `${Math.max(0, window.innerHeight - bounds.top - 16)}px`;
    }

    function closeMenu(restoreFocus = false) {
      menu.hidden = true;
      button.setAttribute("aria-expanded", "false");
      if (restoreFocus || menu.contains(document.activeElement)) button.focus();
    }

    button.addEventListener("click", () => {
      if (!menu.hidden) {
        closeMenu(true);
        return;
      }
      menu.hidden = false;
      button.setAttribute("aria-expanded", "true");
      positionMenu();
      $("#themeBtn").focus();
    });
    // Dialogs launched from Settings stay above the disclosure. Their native
    // close behavior returns focus to the still-visible originating control.
    document.addEventListener("click", (event) => {
      // A dialog's Close/Apply click still bubbles after it has been closed.
      if (!menu.hidden && !control.contains(event.target) && !event.target.closest("dialog") &&
          !document.querySelector("dialog[open]")) {
        closeMenu();
      }
    });
    document.addEventListener("focusin", (event) => {
      if (!menu.hidden && !control.contains(event.target) && !document.querySelector("dialog[open]")) {
        closeMenu();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !menu.hidden && !document.querySelector("dialog[open]")) {
        event.preventDefault();
        closeMenu(true);
      }
    });
    window.addEventListener("resize", positionMenu);

    $("#clearMemoryBtn").addEventListener("click", () => {
      status.textContent = "";
      dialog.showModal();
      $("#cancelClearMemory").focus();
    });
    for (const id of ["#closeClearMemory", "#cancelClearMemory"]) {
      $(id).addEventListener("click", () => dialog.close());
    }
    $("#confirmClearMemory").addEventListener("click", () => {
      const failed = clearBrowserMemory();
      if (failed.length) {
        status.textContent = "Some browser data could not be cleared. Accessible data may already have been removed. Check this site's browser storage permissions and try again. Server bookmarks are unchanged; the page has not reloaded.";
        return;
      }
      window.location.reload();
    });
  }

  globalThis.KellmarksEnhancements = Object.freeze({
    THEMES: Object.freeze(THEMES), THEME_KEY, siteHost, faviconURL, suggestTags,
    loadSiteRules, normalizeTheme, contrast, setupThemes, setupVersionCheck, clearBrowserMemory
  });
  // The disclosure is independent of API startup and also works on static hosts.
  if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", setupSettings, { once: true });
  }
})();
