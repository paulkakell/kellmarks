(() => {
  "use strict";

  const APP_VERSION = "02.00.00";
  const AUTH_KEY = "kellmarks_api_token_v1";
  const LOCAL_KEY = "kellmarks_local_fallback_v2";
  const MAX_IMPORT_BYTES = 1_048_576;
  const MAX_IMPORT_ENTRIES = 5_000;
  const MAX_TAGS = 32;

  const API = {
    health: "/api/health",
    entries: "/api/entries",
    entry: (id) => `/api/entries/${encodeURIComponent(id)}`,
    export: "/api/export",
    import: "/api/import",
    ddg: (query) => `/api/external/ddg?q=${encodeURIComponent(query)}`,
    sample: "assets/sample-data.json"
  };

  class HTTPError extends Error {
    constructor(status, message) {
      super(message);
      this.name = "HTTPError";
      this.status = status;
    }
  }

  const $ = (selector) => document.querySelector(selector);
  const treeElement = $("#tree");
  const cardsElement = $("#cards");
  const emptyElement = $("#empty");
  const queryElement = $("#q");
  const viewTitleElement = $("#viewTitle");
  const viewMetaElement = $("#viewMeta");
  const hintElement = $("#hint");
  const bannerElement = $("#banner");
  const bannerTextElement = $("#bannerText");
  const ddgPanel = $("#ddgPanel");
  const ddgIntro = $("#ddgIntro");
  const ddgList = $("#ddgList");
  const ddgNote = $("#ddgNote");
  const ddgStatus = $("#ddgStatus");
  const dialog = $("#editor");
  const form = $("#form");
  const titleInput = $("#title");
  const urlInput = $("#url");
  const iconInput = $("#icon");
  const tagsInput = $("#tags");
  const descriptionInput = $("#desc");
  const modalTitle = $("#modalTitle");
  const filePicker = $("#filePick");
  const toast = $("#toast");

  const state = {
    entries: [],
    activePath: "__ALL__",
    activeQuery: "",
    editingId: null,
    ddgAbort: null,
    apiReady: false,
    authenticationCancelled: false
  };

  function nowISO() {
    return new Date().toISOString();
  }

  function uid() {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
      return `e-${globalThis.crypto.randomUUID().replaceAll("-", "")}`;
    }
    return `e-${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function readAuthToken() {
    try {
      return sessionStorage.getItem(AUTH_KEY) || "";
    } catch (_error) {
      return "";
    }
  }

  function storeAuthToken(token) {
    try {
      sessionStorage.setItem(AUTH_KEY, token);
    } catch (_error) {
      // A private browsing policy may block session storage. The current request still uses the token.
    }
  }

  function requestAuthToken() {
    const token = window.prompt("Enter the Kellmarks API token for this browser session:");
    if (!token) {
      state.authenticationCancelled = true;
      return "";
    }
    if (token.length < 32) {
      showToast("The API token must contain at least 32 characters");
      return "";
    }
    storeAuthToken(token);
    return token;
  }

  function safeURL(value, required = true) {
    const text = String(value || "").trim();
    if (!text && !required) {
      return "";
    }
    if (/[\\\s]/u.test(text) || /%(?![0-9A-Fa-f]{2})/u.test(text)) {
      return null;
    }
    try {
      const parsed = new URL(text);
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        return null;
      }
      if (parsed.username || parsed.password || !parsed.hostname) {
        return null;
      }
      return parsed.href;
    } catch (_error) {
      return null;
    }
  }

  function normalizeTags(value) {
    const values = Array.isArray(value) ? value : String(value || "").split(",");
    const seen = new Set();
    const tags = [];
    for (const raw of values.slice(0, MAX_TAGS + 1)) {
      const tag = String(raw || "").trim().replace(/\s+/g, " ");
      if (!tag || tag.length > 80 || tag.startsWith("/") || tag.endsWith("/") || tag.includes("//")) {
        continue;
      }
      const key = tag.toLocaleLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        tags.push(tag);
      }
    }
    return tags.slice(0, MAX_TAGS);
  }

  function cleanEntry(value) {
    if (!value || typeof value !== "object") {
      return null;
    }
    const url = safeURL(value.url);
    const iconUrl = safeURL(value.iconUrl, false);
    if (!url || iconUrl === null) {
      return null;
    }
    const rawId = String(value.id || "").trim();
    const id = /^[A-Za-z0-9._:-]{1,80}$/u.test(rawId) ? rawId : uid();
    return {
      id,
      title: String(value.title || url).trim().slice(0, 120) || url,
      url,
      iconUrl,
      description: String(value.description || "").trim().slice(0, 600),
      tags: normalizeTags(value.tags),
      createdAt: String(value.createdAt || nowISO()).slice(0, 64),
      updatedAt: String(value.updatedAt || nowISO()).slice(0, 64)
    };
  }

  async function apiFetch(url, options = {}, allowAuthRetry = true) {
    const headers = new Headers(options.headers || {});
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const token = readAuthToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(url, { ...options, headers, cache: "no-store" });
    if (response.status === 401 && allowAuthRetry && !state.authenticationCancelled) {
      const supplied = requestAuthToken();
      if (supplied) {
        headers.set("Authorization", `Bearer ${supplied}`);
        return apiFetch(url, { ...options, headers }, false);
      }
    }
    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        if (body && body.error) {
          message = body.error;
        }
      } catch (_error) {
        // Retain the status-only message for non-JSON failures.
      }
      throw new HTTPError(response.status, message);
    }
    const contentType = response.headers.get("content-type") || "";
    return contentType.includes("application/json") ? response.json() : response.text();
  }

  function showBanner(kind, message, linkText = "", linkHref = "") {
    bannerElement.style.display = "block";
    bannerElement.dataset.kind = kind;
    bannerTextElement.replaceChildren(document.createTextNode(message));
    if (linkText && linkHref) {
      bannerTextElement.appendChild(document.createTextNode(" "));
      const link = document.createElement("a");
      link.href = linkHref;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = linkText;
      bannerTextElement.appendChild(link);
    }
  }

  function hideBanner() {
    bannerElement.style.display = "none";
    bannerElement.dataset.kind = "";
    bannerTextElement.replaceChildren();
  }

  function saveLocalEntries() {
    try {
      localStorage.setItem(LOCAL_KEY, JSON.stringify(state.entries));
    } catch (_error) {
      showToast("Browser storage is unavailable");
    }
  }

  async function loadFallback() {
    try {
      const response = await fetch(API.sample, { cache: "no-store" });
      if (response.ok) {
        const body = await response.json();
        const list = Array.isArray(body) ? body : body.entries;
        if (Array.isArray(list)) {
          state.entries = list.map(cleanEntry).filter(Boolean);
        }
      }
    } catch (_error) {
      state.entries = [];
    }

    try {
      const raw = localStorage.getItem(LOCAL_KEY);
      if (raw) {
        const list = JSON.parse(raw);
        if (Array.isArray(list)) {
          state.entries = list.map(cleanEntry).filter(Boolean);
        }
      }
    } catch (_error) {
      // A corrupt local cache is ignored rather than executed or merged.
    }
  }

  async function initializeData() {
    try {
      await apiFetch(API.health, { method: "GET" });
      state.entries = await apiFetch(API.entries, { method: "GET" });
      state.entries = state.entries.map(cleanEntry).filter(Boolean);
      state.apiReady = true;
      hideBanner();
      return;
    } catch (error) {
      state.apiReady = false;
      if (error instanceof HTTPError && [401, 403].includes(error.status)) {
        state.entries = [];
        showBanner("locked", "The API is protected. Reload and enter a valid session token to continue.");
        return;
      }
    }

    await loadFallback();
    if (location.protocol === "file:") {
      showBanner("file", "Read-only file mode. Run the local server for protected persistence.");
    } else {
      showBanner(
        "noapi",
        "API unavailable. Changes are stored only in this browser.",
        "Server guide",
        "https://github.com/paulkakell/kellmarks/blob/dev/docs/server/README.md"
      );
    }
  }

  function entryText(entry) {
    return [entry.title, entry.url, entry.description, ...(entry.tags || [])].join(" ").toLowerCase();
  }

  function tokenize(query) {
    const text = String(query || "").trim();
    const output = [];
    let index = 0;
    while (index < text.length) {
      const character = text[index];
      if (/\s/.test(character)) {
        index += 1;
        continue;
      }
      if (character === "(" || character === ")") {
        output.push({ type: character });
        index += 1;
        continue;
      }
      if (character === '"') {
        let end = index + 1;
        let buffer = "";
        while (end < text.length && text[end] !== '"') {
          buffer += text[end];
          end += 1;
        }
        output.push({ type: "TERM", value: buffer.toLowerCase() });
        index = end < text.length ? end + 1 : end;
        continue;
      }
      let end = index;
      let word = "";
      while (end < text.length && !/\s|\(|\)/.test(text[end])) {
        word += text[end];
        end += 1;
      }
      const upper = word.toUpperCase();
      output.push(
        ["AND", "OR", "NOT"].includes(upper)
          ? { type: upper }
          : { type: "TERM", value: word.toLowerCase() }
      );
      index = end;
    }

    const withAnd = [];
    for (let position = 0; position < output.length; position += 1) {
      const token = output[position];
      const next = output[position + 1];
      withAnd.push(token);
      if (!next) {
        continue;
      }
      if (["TERM", ")"].includes(token.type) && ["TERM", "(", "NOT"].includes(next.type)) {
        withAnd.push({ type: "AND" });
      }
    }
    return withAnd;
  }

  function toRPN(tokens) {
    const precedence = { NOT: 3, AND: 2, OR: 1 };
    const output = [];
    const operators = [];
    for (const token of tokens) {
      if (token.type === "TERM") {
        output.push(token);
      } else if (token.type === "(") {
        operators.push(token);
      } else if (token.type === ")") {
        while (operators.length && operators.at(-1).type !== "(") {
          output.push(operators.pop());
        }
        if (operators.length && operators.at(-1).type === "(") {
          operators.pop();
        }
      } else {
        while (operators.length && operators.at(-1).type !== "(") {
          const top = operators.at(-1).type;
          if (precedence[top] > precedence[token.type] || (precedence[top] === precedence[token.type] && token.type !== "NOT")) {
            output.push(operators.pop());
          } else {
            break;
          }
        }
        operators.push(token);
      }
    }
    while (operators.length) {
      const operator = operators.pop();
      if (!["(", ")"].includes(operator.type)) {
        output.push(operator);
      }
    }
    return output;
  }

  function evaluateRPN(rpn, text) {
    const stack = [];
    for (const token of rpn) {
      if (token.type === "TERM") {
        stack.push(token.value ? text.includes(token.value) : true);
      } else if (token.type === "NOT") {
        stack.push(!Boolean(stack.pop()));
      } else {
        const right = Boolean(stack.pop());
        const left = Boolean(stack.pop());
        stack.push(token.type === "AND" ? left && right : left || right);
      }
    }
    return stack.length ? Boolean(stack.at(-1)) : true;
  }

  function matchesQuery(entry, query) {
    const text = String(query || "").trim();
    return !text || evaluateRPN(toRPN(tokenize(text)), entryText(entry));
  }

  function splitPath(path) {
    return String(path || "").split("/").map((part) => part.trim()).filter(Boolean);
  }

  function buildTree(entries) {
    const root = { name: "All", path: "__ALL__", children: new Map(), ids: new Set() };
    const untagged = { name: "Untagged", path: "Untagged", children: new Map(), ids: new Set() };
    root.children.set("Untagged", untagged);
    for (const entry of entries) {
      root.ids.add(entry.id);
      if (!entry.tags.length) {
        untagged.ids.add(entry.id);
        continue;
      }
      for (const rawTag of entry.tags) {
        let current = root;
        let accumulated = "";
        for (const part of splitPath(rawTag)) {
          accumulated = accumulated ? `${accumulated}/${part}` : part;
          if (!current.children.has(part)) {
            current.children.set(part, { name: part, path: accumulated, children: new Map(), ids: new Set() });
          }
          current = current.children.get(part);
          current.ids.add(entry.id);
        }
      }
    }
    return root;
  }

  function renderTree() {
    treeElement.replaceChildren();
    const tree = buildTree(state.entries);

    function renderNode(node, depth, canCollapse) {
      const row = document.createElement("div");
      row.className = `node${state.activePath === node.path ? " active" : ""}`;
      row.style.marginLeft = depth ? `${depth * 14}px` : "0";

      const twisty = document.createElement("div");
      twisty.className = "twisty";
      const hasChildren = Boolean(node.children && node.children.size);
      let open = true;
      twisty.textContent = hasChildren && canCollapse ? "v" : hasChildren ? ">" : " ";

      const label = document.createElement("div");
      label.className = "label";
      label.textContent = node.path === "__ALL__" ? "All" : node.name;

      const count = document.createElement("div");
      count.className = "count";
      count.textContent = String(node.ids ? node.ids.size : 0);

      row.append(twisty, label, count);
      row.addEventListener("click", (event) => {
        if (event.target === twisty && hasChildren && canCollapse) {
          open = !open;
          twisty.textContent = open ? "v" : ">";
          event.stopPropagation();
          return;
        }
        state.activePath = node.path;
        renderTree();
        renderCards();
      });
      treeElement.appendChild(row);

      if (hasChildren && open) {
        const children = [...node.children.values()].sort((left, right) => (
          right.ids.size - left.ids.size || left.name.localeCompare(right.name)
        ));
        for (const child of children) {
          renderNode(child, depth + 1, true);
        }
      }
    }

    renderNode(tree, 0, false);
  }

  function filteredEntries() {
    let entries = state.entries.filter((entry) => matchesQuery(entry, state.activeQuery));
    if (state.activePath === "Untagged") {
      entries = entries.filter((entry) => !entry.tags.length);
    } else if (state.activePath !== "__ALL__") {
      entries = entries.filter((entry) => entry.tags.some((tag) => (
        tag === state.activePath || tag.startsWith(`${state.activePath}/`)
      )));
    }
    return entries.toSorted((left, right) => left.title.localeCompare(right.title));
  }

  function initials(value) {
    const parts = String(value || "").trim().split(/\s+/).filter(Boolean);
    return `${(parts[0] || "K")[0]}${(parts[1] || parts[0] || "M")[0]}`.toUpperCase();
  }

  function createCard(entry) {
    const card = document.createElement("div");
    card.className = "card";
    const row = document.createElement("div");
    row.className = "row1";
    const icon = document.createElement("div");
    icon.className = "icon";

    function addFallbackIcon() {
      icon.replaceChildren();
      const fallback = document.createElement("div");
      fallback.className = "fallback";
      fallback.textContent = initials(entry.title || "Link");
      icon.appendChild(fallback);
    }

    if (entry.iconUrl) {
      const image = document.createElement("img");
      image.alt = "";
      image.referrerPolicy = "no-referrer";
      image.src = entry.iconUrl;
      image.addEventListener("error", addFallbackIcon, { once: true });
      icon.appendChild(image);
    } else {
      addFallbackIcon();
    }

    const body = document.createElement("div");
    body.style.minWidth = "0";
    body.style.flex = "1";
    const heading = document.createElement("h3");
    const link = document.createElement("a");
    link.href = entry.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = entry.title || entry.url;
    heading.appendChild(link);
    const url = document.createElement("div");
    url.className = "url";
    url.textContent = entry.url;
    const description = document.createElement("p");
    description.className = "desc";
    description.textContent = entry.description;
    body.append(heading, url, description);
    row.append(icon, body);

    const chips = document.createElement("div");
    chips.className = "chips";
    for (const tag of entry.tags) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.textContent = tag;
      chip.title = `View tag: ${tag}`;
      chip.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        state.activePath = tag;
        renderTree();
        renderCards();
      });
      chips.appendChild(chip);
    }

    const actions = document.createElement("div");
    actions.className = "card-actions";
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "mini";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => openEditor(entry.id));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "mini";
    remove.textContent = "Delete";
    remove.addEventListener("click", () => deleteEntry(entry.id));
    actions.append(edit, remove);

    card.appendChild(row);
    if (entry.tags.length) {
      card.appendChild(chips);
    }
    card.appendChild(actions);
    return card;
  }

  function renderCards() {
    const entries = filteredEntries();
    const query = state.activeQuery.trim();
    viewTitleElement.textContent = state.activePath === "__ALL__" ? "All" : state.activePath;
    viewMetaElement.textContent = `${entries.length} match${entries.length === 1 ? "" : "es"}${query ? ` for "${query}"` : ""}`;
    hintElement.textContent = `Kellmarks ${APP_VERSION}. Search supports AND, OR, NOT, and parentheses.`;
    cardsElement.replaceChildren();
    emptyElement.style.display = entries.length ? "none" : "block";
    emptyElement.textContent = state.entries.length
      ? "No matches. Adjust the query or tag path."
      : "No entries are available.";
    for (const entry of entries) {
      cardsElement.appendChild(createCard(entry));
    }
    if (query && query.length <= 256 && state.apiReady) {
      renderDDG(query);
    } else {
      ddgPanel.style.display = "none";
      abortDDG();
    }
  }

  function openEditor(id = null) {
    if (!state.apiReady && location.protocol === "file:") {
      showToast("Read-only file mode");
      return;
    }
    state.editingId = id;
    const entry = id ? state.entries.find((candidate) => candidate.id === id) : null;
    modalTitle.textContent = id ? "Edit entry" : "Add entry";
    titleInput.value = entry?.title || "";
    urlInput.value = entry?.url || "";
    iconInput.value = entry?.iconUrl || "";
    tagsInput.value = (entry?.tags || []).join(", ");
    descriptionInput.value = entry?.description || "";
    try {
      dialog.showModal();
    } catch (_error) {
      dialog.setAttribute("open", "open");
    }
    window.setTimeout(() => titleInput.focus(), 60);
  }

  function closeEditor() {
    try {
      dialog.close();
    } catch (_error) {
      dialog.removeAttribute("open");
    }
    state.editingId = null;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const url = safeURL(urlInput.value);
    const iconUrl = safeURL(iconInput.value, false);
    if (!url || iconUrl === null) {
      showToast("URLs must use HTTP or HTTPS and must not include credentials");
      urlInput.focus();
      return;
    }
    const tags = normalizeTags(tagsInput.value);
    if (String(tagsInput.value).split(",").filter((tag) => tag.trim()).length > MAX_TAGS) {
      showToast(`No more than ${MAX_TAGS} tags are allowed`);
      return;
    }
    const payload = {
      title: titleInput.value.trim().slice(0, 120),
      url,
      iconUrl,
      description: descriptionInput.value.trim().slice(0, 600),
      tags
    };
    const editingId = state.editingId;
    try {
      if (state.apiReady) {
        await apiFetch(editingId ? API.entry(editingId) : API.entries, {
          method: editingId ? "PUT" : "POST",
          body: JSON.stringify(payload)
        });
        state.entries = (await apiFetch(API.entries)).map(cleanEntry).filter(Boolean);
      } else if (editingId) {
        const index = state.entries.findIndex((entry) => entry.id === editingId);
        if (index >= 0) {
          state.entries[index] = { ...state.entries[index], ...payload, updatedAt: nowISO() };
        }
        saveLocalEntries();
      } else {
        state.entries.unshift({ id: uid(), createdAt: nowISO(), updatedAt: nowISO(), ...payload });
        saveLocalEntries();
      }
      closeEditor();
      renderTree();
      renderCards();
      showToast(editingId ? "Updated" : "Added");
    } catch (error) {
      showToast(error.message || "Save failed");
    }
  });

  async function deleteEntry(id) {
    const entry = state.entries.find((candidate) => candidate.id === id);
    if (!entry || !window.confirm(`Delete "${entry.title || entry.url}"?`)) {
      return;
    }
    try {
      if (state.apiReady) {
        await apiFetch(API.entry(id), { method: "DELETE" });
        state.entries = (await apiFetch(API.entries)).map(cleanEntry).filter(Boolean);
      } else {
        state.entries = state.entries.filter((candidate) => candidate.id !== id);
        saveLocalEntries();
      }
      renderTree();
      renderCards();
      showToast("Deleted");
    } catch (error) {
      showToast(error.message || "Delete failed");
    }
  }

  $("#addBtn").addEventListener("click", () => openEditor());
  $("#closeModal").addEventListener("click", closeEditor);
  $("#cancelBtn").addEventListener("click", closeEditor);

  let searchTimer = null;
  queryElement.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.activeQuery = queryElement.value.slice(0, 512);
      renderCards();
    }, 140);
  });

  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === "k") {
      event.preventDefault();
      queryElement.focus();
      queryElement.select();
    }
    if (event.key === "Escape" && dialog.open) {
      closeEditor();
    }
  });

  function downloadJSON(data) {
    const blob = new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: "application/json" });
    const link = document.createElement("a");
    const objectURL = URL.createObjectURL(blob);
    link.href = objectURL;
    link.download = `kellmarks-${APP_VERSION}-export.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(objectURL), 0);
  }

  $("#exportBtn").addEventListener("click", async () => {
    try {
      const data = state.apiReady
        ? await apiFetch(API.export)
        : { version: 2, exportedAt: nowISO(), entries: state.entries };
      downloadJSON(data);
    } catch (error) {
      showToast(error.message || "Export failed");
    }
  });

  $("#importBtn").addEventListener("click", () => filePicker.click());
  filePicker.addEventListener("change", async () => {
    const file = filePicker.files?.[0];
    if (!file) {
      return;
    }
    try {
      if (file.size > MAX_IMPORT_BYTES) {
        throw new Error("Import file exceeds 1 MiB");
      }
      const parsed = JSON.parse(await file.text());
      const list = Array.isArray(parsed) ? parsed : parsed.entries;
      if (!Array.isArray(list) || list.length > MAX_IMPORT_ENTRIES) {
        throw new Error(`Import must contain no more than ${MAX_IMPORT_ENTRIES} entries`);
      }
      const cleaned = list.map(cleanEntry);
      if (cleaned.some((entry) => entry === null) || !cleaned.length) {
        throw new Error("Import contains invalid or unsafe URLs");
      }
      const ids = new Set(cleaned.map((entry) => entry.id));
      if (ids.size !== cleaned.length) {
        throw new Error("Import contains duplicate IDs");
      }
      if (!window.confirm(`Import ${cleaned.length} entries? This replaces the current list.`)) {
        return;
      }
      if (state.apiReady) {
        await apiFetch(API.import, { method: "POST", body: JSON.stringify({ entries: cleaned }) });
        state.entries = (await apiFetch(API.entries)).map(cleanEntry).filter(Boolean);
      } else {
        state.entries = cleaned;
        saveLocalEntries();
      }
      state.activePath = "__ALL__";
      renderTree();
      renderCards();
      showToast("Imported");
    } catch (error) {
      showToast(error.message || "Import failed");
    } finally {
      filePicker.value = "";
    }
  });

  function abortDDG() {
    if (state.ddgAbort) {
      state.ddgAbort.abort();
      state.ddgAbort = null;
    }
  }

  async function renderDDG(query) {
    ddgPanel.style.display = "block";
    ddgList.replaceChildren();
    ddgNote.replaceChildren();
    ddgStatus.textContent = "Loading...";
    ddgIntro.replaceChildren(
      document.createTextNode("Searching externally for "),
      Object.assign(document.createElement("strong"), { textContent: query })
    );
    abortDDG();
    const controller = new AbortController();
    state.ddgAbort = controller;
    try {
      const data = await apiFetch(API.ddg(query), { signal: controller.signal });
      const items = Array.isArray(data.results) ? data.results : [];
      for (const item of items.slice(0, 10)) {
        const url = safeURL(item.url);
        if (!url) {
          continue;
        }
        const container = document.createElement("div");
        container.className = "ddg-item";
        const title = document.createElement("div");
        title.className = "t";
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = String(item.title || url).slice(0, 140);
        title.appendChild(link);
        const snippet = document.createElement("div");
        snippet.className = "s";
        snippet.textContent = String(item.snippet || "").slice(0, 280);
        container.append(title, snippet);
        ddgList.appendChild(container);
      }
      ddgStatus.textContent = `${ddgList.children.length} result${ddgList.children.length === 1 ? "" : "s"}`;
      const fullResults = document.createElement("a");
      fullResults.href = `https://duckduckgo.com/?q=${encodeURIComponent(query)}`;
      fullResults.target = "_blank";
      fullResults.rel = "noopener noreferrer";
      fullResults.textContent = "Open full DuckDuckGo results";
      ddgNote.appendChild(fullResults);
    } catch (error) {
      if (error.name !== "AbortError") {
        ddgStatus.textContent = "Unavailable";
      }
    } finally {
      if (state.ddgAbort === controller) {
        state.ddgAbort = null;
      }
    }
  }

  async function boot() {
    await initializeData();
    renderTree();
    renderCards();
  }

  boot().catch(() => {
    showBanner("error", "Kellmarks could not initialize safely.");
  });
})();
