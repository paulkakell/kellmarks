(() => {
  const API = {
    base: "",
    health: () => `${API.base}/api/health`,
    listEntries: () => `${API.base}/api/entries`,
    getEntry: (id) => `${API.base}/api/entries/${encodeURIComponent(id)}`,
    createEntry: () => `${API.base}/api/entries`,
    updateEntry: (id) => `${API.base}/api/entries/${encodeURIComponent(id)}`,
    deleteEntry: (id) => `${API.base}/api/entries/${encodeURIComponent(id)}`,
    exportAll: () => `${API.base}/api/export`,
    importAll: () => `${API.base}/api/import`,
    tagsTree: () => `${API.base}/api/tags/tree`,
    search: () => `${API.base}/api/search`,
    ddg: (q) => `${API.base}/api/external/ddg?q=${encodeURIComponent(q)}`,
    staticDataFallback: () => `assets/data.json`
  };

  const LS_KEY = "kellmarks_local_fallback_v1";

  const $ = (sel) => document.querySelector(sel);
  const elTree = $("#tree");
  const elCards = $("#cards");
  const elEmpty = $("#empty");
  const elQ = $("#q");
  const elViewTitle = $("#viewTitle");
  const elViewMeta = $("#viewMeta");
  const elHint = $("#hint");
  const banner = $("#banner");
  const bannerText = $("#bannerText");

  const ddgPanel = $("#ddgPanel");
  const ddgIntro = $("#ddgIntro");
  const ddgList = $("#ddgList");
  const ddgNote = $("#ddgNote");
  const ddgStatus = $("#ddgStatus");

  const dlg = $("#editor");
  const form = $("#form");
  const inTitle = $("#title");
  const inUrl = $("#url");
  const inIcon = $("#icon");
  const inTags = $("#tags");
  const inDesc = $("#desc");
  const modalTitle = $("#modalTitle");
  const filePick = $("#filePick");
  const toast = $("#toast");

  const state = {
    entries: [],
    activePath: "__ALL__",
    activeQuery: "",
    editingId: null,
    ddgAbort: null,
    apiReady: false
  };

  const nowISO = () => new Date().toISOString();
  const uid = () => (crypto?.randomUUID ? crypto.randomUUID() : ("id-" + Math.random().toString(16).slice(2) + Date.now().toString(16)));

  function showToast(msg){
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function safeURL(u){
    try{
      const url = new URL(u);
      return url.href;
    }catch(e){
      return null;
    }
  }

  function normalizeTags(s){
    return (s || "")
      .split(",")
      .map(x => x.trim())
      .filter(Boolean)
      .map(x => x.replace(/\s+/g, " "));
  }

  function splitPath(path){
    return (path || "").split("/").map(s => s.trim()).filter(Boolean);
  }

  function entryText(entry){
    const fields = [
      entry.title || "",
      entry.url || "",
      entry.description || "",
      (entry.tags || []).join(" ")
    ];
    return fields.join(" ").toLowerCase();
  }

  async function apiFetch(url, opts){
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...opts
    });
    if(!res.ok){
      const t = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status} ${t}`);
    }
    const ct = res.headers.get("content-type") || "";
    if(ct.includes("application/json")) return res.json();
    return res.text();
  }

  async function loadFromApi(){
    const r = await apiFetch(API.listEntries(), { method:"GET" });
    const list = Array.isArray(r) ? r : r.entries;
    if(!Array.isArray(list)) throw new Error("Bad entries payload");
    state.entries = list;
  }

  async function loadFallback(){
    try{
      const r = await fetch(API.staticDataFallback(), { cache:"no-store" });
      if(r.ok){
        const obj = await r.json();
        const list = Array.isArray(obj) ? obj : obj.entries;
        if(Array.isArray(list) && list.length){
          state.entries = list;
          return;
        }
      }
    }catch(e){}

    try{
      const raw = localStorage.getItem(LS_KEY);
      if(raw){
        const list = JSON.parse(raw);
        if(Array.isArray(list)) state.entries = list;
      }
    }catch(e){}
  }

  function saveFallback(){
    try{
      localStorage.setItem(LS_KEY, JSON.stringify(state.entries));
    }catch(e){}
  }

  function showBanner(kind, msg, linkText, linkHref){
    banner.style.display = "block";
    banner.dataset.kind = kind;
    if(linkText && linkHref){
      bannerText.innerHTML = `${escapeHTML(msg)} <a href="${linkHref}" target="_blank" rel="noopener noreferrer">${escapeHTML(linkText)}</a>`;
    }else{
      bannerText.textContent = msg;
    }
  }

  function hideBanner(){
    banner.style.display = "none";
    bannerText.textContent = "";
    banner.dataset.kind = "";
  }

  async function initData(){
    try{
      await apiFetch(API.health(), { method:"GET" });
      state.apiReady = true;
      hideBanner();
      await loadFromApi();
    }catch(e){
      state.apiReady = false;
      await loadFallback();

      const isFile = location.protocol === "file:";
      if(isFile){
        showBanner(
          "file",
          "Read only mode. File path pages cannot write to assets/data.json. Run the included server for edits.",
          "Server quickstart",
          "server/README.md"
        );
      }else{
        showBanner(
          "noapi",
          "API not reachable. Using local fallback storage. Start the server to enable shared JSON persistence.",
          "Server quickstart",
          "server/README.md"
        );
      }
    }

    if(!state.entries.length){
      state.entries = [];
    }
  }

  // Boolean query parsing
  function tokenize(q){
    const s = (q || "").trim();
    const out = [];
    let i = 0;
    while(i < s.length){
      const c = s[i];
      if(/\s/.test(c)){ i++; continue; }
      if(c === "(" || c === ")"){ out.push({type:c}); i++; continue; }
      if(c === '"'){
        let j = i + 1, buf = "";
        while(j < s.length && s[j] !== '"'){ buf += s[j]; j++; }
        out.push({type:"TERM", value: buf.toLowerCase()});
        i = (j < s.length) ? j + 1 : j;
        continue;
      }
      let j = i, w = "";
      while(j < s.length && !/\s|\(|\)/.test(s[j])){ w += s[j]; j++; }
      const up = w.toUpperCase();
      if(up === "AND" || up === "OR" || up === "NOT") out.push({type: up});
      else out.push({type:"TERM", value: w.toLowerCase()});
      i = j;
    }
    const withAnd = [];
    for(let k=0; k<out.length; k++){
      const a = out[k];
      const b = out[k+1];
      withAnd.push(a);
      if(!b) break;
      const aIs = (a.type === "TERM" || a.type === ")");
      const bIs = (b.type === "TERM" || b.type === "(" || b.type === "NOT");
      if(aIs && bIs) withAnd.push({type:"AND"});
    }
    return withAnd;
  }

  function toRPN(tokens){
    const prec = { "NOT": 3, "AND": 2, "OR": 1 };
    const rightAssoc = { "NOT": true };
    const out = [];
    const ops = [];
    for(const t of tokens){
      if(t.type === "TERM"){ out.push(t); continue; }
      if(t.type === "("){ ops.push(t); continue; }
      if(t.type === ")"){
        while(ops.length && ops[ops.length-1].type !== "(") out.push(ops.pop());
        if(ops.length && ops[ops.length-1].type === "(") ops.pop();
        continue;
      }
      if(t.type === "AND" || t.type === "OR" || t.type === "NOT"){
        while(ops.length){
          const top = ops[ops.length-1].type;
          if(top === "(") break;
          const pTop = prec[top] || 0;
          const pT = prec[t.type] || 0;
          if(pTop > pT || (pTop === pT && !rightAssoc[t.type])) out.push(ops.pop());
          else break;
        }
        ops.push(t);
      }
    }
    while(ops.length) out.push(ops.pop());
    return out;
  }

  function evalRPN(rpn, text){
    const st = [];
    for(const t of rpn){
      if(t.type === "TERM"){ st.push(t.value ? text.includes(t.value) : true); continue; }
      if(t.type === "NOT"){ st.push(!st.pop()); continue; }
      if(t.type === "AND"){ const b = st.pop(), a = st.pop(); st.push(Boolean(a && b)); continue; }
      if(t.type === "OR"){ const b = st.pop(), a = st.pop(); st.push(Boolean(a || b)); continue; }
    }
    return st.length ? Boolean(st[st.length-1]) : true;
  }

  function matchesQuery(entry, q){
    const query = (q || "").trim();
    if(!query) return true;
    const tokens = tokenize(query);
    if(!tokens.length) return true;
    const rpn = toRPN(tokens);
    return evalRPN(rpn, entryText(entry));
  }

  function buildTree(entries){
    const root = { name: "All", path: "__ALL__", children: new Map(), ids: new Set() };
    const untagged = { name: "Untagged", path: "Untagged", children: new Map(), ids: new Set() };
    root.children.set("Untagged", untagged);

    for(const e of entries){
      if(!e || !e.id) continue;
      root.ids.add(e.id);

      const tags = Array.isArray(e.tags) ? e.tags : [];
      if(!tags.length){
        untagged.ids.add(e.id);
        continue;
      }

      for(const raw of tags){
        const tag = String(raw || "").trim();
        if(!tag) continue;
        const parts = splitPath(tag);
        if(!parts.length) continue;

        let cur = root;
        let acc = "";
        for(const part of parts){
          acc = acc ? (acc + "/" + part) : part;
          if(!cur.children.has(part)){
            cur.children.set(part, { name: part, path: acc, children: new Map(), ids: new Set() });
          }
          const child = cur.children.get(part);
          child.ids.add(e.id);
          cur = child;
        }
      }
    }
    return root;
  }

  function renderTree(){
    elTree.innerHTML = "";
    const tree = buildTree(state.entries);

    const renderNode = (node, depth, canCollapse) => {
      const row = document.createElement("div");
      row.className = "node" + (state.activePath === node.path ? " active" : "");
      row.style.marginLeft = depth ? (depth * 14 + "px") : "0";

      const twisty = document.createElement("div");
      twisty.className = "twisty";
      const hasKids = node.children && node.children.size;
      let open = true;
      twisty.textContent = (hasKids && canCollapse) ? "v" : (hasKids ? ">" : " ");

      const label = document.createElement("div");
      label.className = "label";
      label.textContent = node.path === "__ALL__" ? "All" : node.name;

      const count = document.createElement("div");
      count.className = "count";
      count.textContent = String(node.ids ? node.ids.size : 0);

      row.appendChild(twisty);
      row.appendChild(label);
      row.appendChild(count);

      const setOpen = (v) => {
        open = v;
        if(hasKids && canCollapse) twisty.textContent = open ? "v" : ">";
      };

      row.addEventListener("click", (ev) => {
        const onTwisty = ev.target === twisty;
        if(onTwisty && hasKids && canCollapse){
          setOpen(!open);
          ev.stopPropagation();
          return;
        }
        state.activePath = node.path;
        renderTree();
        renderCards();
      });

      elTree.appendChild(row);

      if(hasKids){
        const kids = [...node.children.values()];
        kids.sort((a,b) => (((b.ids ? b.ids.size : 0) - (a.ids ? a.ids.size : 0)) || a.name.localeCompare(b.name)));
        for(const kid of kids) renderNode(kid, depth + 1, true);
      }
    };

    renderNode(tree, 0, false);
  }

  function filteredEntries(){
    const q = state.activeQuery;
    let list = state.entries.filter(e => matchesQuery(e, q));

    if(state.activePath && state.activePath !== "__ALL__"){
      if(state.activePath === "Untagged"){
        list = list.filter(e => !(e.tags && e.tags.length));
      }else{
        const prefix = state.activePath;
        list = list.filter(e => (e.tags || []).some(t => {
          const s = String(t || "");
          return (s === prefix) || s.startsWith(prefix + "/");
        }));
      }
    }

    list.sort((a,b) => (a.title || "").localeCompare(b.title || ""));
    return list;
  }

  function initials(s){
    const parts = (s || "").trim().split(/\s+/).filter(Boolean);
    const a = (parts[0] || "K")[0] || "K";
    const b = (parts[1] || parts[0] || "M")[0] || "M";
    return (a + b).toUpperCase();
  }

  function cardEl(entry){
    const card = document.createElement("div");
    card.className = "card";

    const row1 = document.createElement("div");
    row1.className = "row1";

    const icon = document.createElement("div");
    icon.className = "icon";

    if(entry.iconUrl){
      const img = document.createElement("img");
      img.alt = "";
      img.referrerPolicy = "no-referrer";
      img.src = entry.iconUrl;
      img.onerror = () => {
        icon.innerHTML = "";
        const fb = document.createElement("div");
        fb.className = "fallback";
        fb.textContent = initials(entry.title || "Link");
        icon.appendChild(fb);
      };
      icon.appendChild(img);
    }else{
      const fb = document.createElement("div");
      fb.className = "fallback";
      fb.textContent = initials(entry.title || "Link");
      icon.appendChild(fb);
    }

    const body = document.createElement("div");
    body.style.minWidth = "0";
    body.style.flex = "1";

    const h3 = document.createElement("h3");
    const a = document.createElement("a");
    a.href = entry.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = entry.title || entry.url;
    h3.appendChild(a);

    const url = document.createElement("div");
    url.className = "url";
    url.textContent = entry.url;

    const desc = document.createElement("p");
    desc.className = "desc";
    desc.textContent = entry.description || "";

    body.appendChild(h3);
    body.appendChild(url);
    body.appendChild(desc);

    row1.appendChild(icon);
    row1.appendChild(body);

    const chips = document.createElement("div");
    chips.className = "chips";
    for(const t of (entry.tags || [])){
      const c = document.createElement("button");
      c.type = "button";
      c.className = "chip";
      c.textContent = t;
      c.title = "View tag: " + t;
      c.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        state.activePath = t;
        renderTree();
        renderCards();
      });
      chips.appendChild(c);
    }

    const actions = document.createElement("div");
    actions.className = "card-actions";

    const edit = document.createElement("button");
    edit.className = "mini";
    edit.type = "button";
    edit.textContent = "Edit";
    edit.onclick = () => openEditor(entry.id);

    const del = document.createElement("button");
    del.className = "mini";
    del.type = "button";
    del.textContent = "Delete";
    del.onclick = () => deleteEntry(entry.id);

    actions.appendChild(edit);
    actions.appendChild(del);

    card.appendChild(row1);
    if((entry.tags || []).length) card.appendChild(chips);
    card.appendChild(actions);
    return card;
  }

  function renderCards(){
    const list = filteredEntries();
    const q = state.activeQuery.trim();
    const pathLabel = state.activePath === "__ALL__" ? "All" : state.activePath;

    elViewTitle.textContent = pathLabel;
    elViewMeta.textContent = `${list.length} match${list.length === 1 ? "" : "es"}${q ? (` for "${q}"`) : ""}`;
    elHint.textContent = "Search supports AND OR NOT and parentheses.";

    elCards.innerHTML = "";
    elEmpty.style.display = "none";

    if(!list.length){
      elEmpty.style.display = "block";
      elEmpty.textContent = state.entries.length
        ? "No matches. Try adjusting the boolean query, or select a different tag path."
        : "No entries yet. Add one to get started.";
    }else{
      for(const e of list) elCards.appendChild(cardEl(e));
    }

    if(q) renderDDG(q);
    else{
      ddgPanel.style.display = "none";
      abortDDG();
    }
  }

  function openEditor(id){
    if(!state.apiReady && location.protocol === "file:"){
      showToast("Read only mode");
      return;
    }
    state.editingId = id || null;
    const e = id ? state.entries.find(x => x.id === id) : null;

    modalTitle.textContent = id ? "Edit entry" : "Add entry";
    inTitle.value = e?.title || "";
    inUrl.value = e?.url || "";
    inIcon.value = e?.iconUrl || "";
    inTags.value = (e?.tags || []).join(", ");
    inDesc.value = e?.description || "";

    try{ dlg.showModal(); }catch(err){ dlg.setAttribute("open", "open"); }
    setTimeout(() => inTitle.focus(), 60);
  }

  function closeEditor(){
    try{ dlg.close(); }catch(err){ dlg.removeAttribute("open"); }
    state.editingId = null;
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();

    const url = safeURL(inUrl.value.trim());
    if(!url){
      showToast("Invalid URL");
      inUrl.focus();
      return;
    }

    const payload = {
      title: inTitle.value.trim(),
      url,
      iconUrl: inIcon.value.trim(),
      description: inDesc.value.trim(),
      tags: normalizeTags(inTags.value)
    };

    if(state.apiReady){
      if(state.editingId){
        await apiFetch(API.updateEntry(state.editingId), { method:"PUT", body: JSON.stringify(payload) });
      }else{
        await apiFetch(API.createEntry(), { method:"POST", body: JSON.stringify(payload) });
      }
      await loadFromApi();
    }else{
      const t = nowISO();
      if(state.editingId){
        const i = state.entries.findIndex(x => x.id === state.editingId);
        if(i >= 0) state.entries[i] = { ...state.entries[i], ...payload, updatedAt: t };
      }else{
        state.entries.unshift({ id: uid(), createdAt: t, updatedAt: t, ...payload });
      }
      saveFallback();
    }

    renderTree();
    renderCards();
    closeEditor();
    showToast(state.editingId ? "Updated" : "Added");
  });

  async function deleteEntry(id){
    const e = state.entries.find(x => x.id === id);
    if(!e) return;
    const ok = confirm(`Delete "${e.title || e.url}"?`);
    if(!ok) return;

    if(state.apiReady){
      await apiFetch(API.deleteEntry(id), { method:"DELETE" });
      await loadFromApi();
    }else{
      state.entries = state.entries.filter(x => x.id !== id);
      saveFallback();
    }

    renderTree();
    renderCards();
    showToast("Deleted");
  }

  $("#addBtn").addEventListener("click", () => openEditor(null));
  $("#closeModal").addEventListener("click", closeEditor);
  $("#cancelBtn").addEventListener("click", closeEditor);

  let searchTimer = null;
  elQ.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.activeQuery = elQ.value || "";
      renderCards();
    }, 140);
  });

  window.addEventListener("keydown", (e) => {
    if((e.ctrlKey || e.metaKey) && (e.key || "").toLowerCase() === "k"){
      e.preventDefault();
      elQ.focus();
      elQ.select();
    }
    if(e.key === "Escape"){
      if(dlg.open) closeEditor();
    }
  });

  $("#exportBtn").addEventListener("click", async () => {
    if(state.apiReady){
      const obj = await apiFetch(API.exportAll(), { method:"GET" });
      const blob = new Blob([JSON.stringify(obj, null, 2)], { type:"application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "kellmarks-export.json";
      a.click();
      URL.revokeObjectURL(a.href);
    }else{
      const obj = { version: 1, exportedAt: nowISO(), entries: state.entries };
      const blob = new Blob([JSON.stringify(obj, null, 2)], { type:"application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "kellmarks-export.json";
      a.click();
      URL.revokeObjectURL(a.href);
    }
  });

  $("#importBtn").addEventListener("click", () => filePick.click());

  filePick.addEventListener("change", async () => {
    const f = filePick.files && filePick.files[0];
    if(!f) return;
    try{
      const text = await f.text();
      const obj = JSON.parse(text);
      const list = Array.isArray(obj) ? obj : obj.entries;
      if(!Array.isArray(list)) throw new Error("Bad file");

      const cleaned = [];
      for(const x of list){
        if(!x) continue;
        const url = safeURL(String(x.url || "").trim());
        if(!url) continue;
        cleaned.push({
          id: String(x.id || uid()),
          title: String(x.title || url).slice(0,120),
          url,
          iconUrl: String(x.iconUrl || "").slice(0,2048),
          description: String(x.description || "").slice(0,600),
          tags: Array.isArray(x.tags) ? x.tags.map(String) : normalizeTags(String(x.tags || "")),
          createdAt: String(x.createdAt || nowISO()),
          updatedAt: String(x.updatedAt || nowISO())
        });
      }
      if(!cleaned.length){
        showToast("No valid entries found");
        return;
      }
      const ok = confirm(`Import ${cleaned.length} entries? This will replace your current list.`);
      if(!ok) return;

      if(state.apiReady){
        await apiFetch(API.importAll(), { method:"POST", body: JSON.stringify({ entries: cleaned }) });
        await loadFromApi();
      }else{
        state.entries = cleaned;
        saveFallback();
      }

      state.activePath = "__ALL__";
      renderTree();
      renderCards();
      showToast("Imported");
    }catch(err){
      showToast("Import failed");
    }finally{
      filePick.value = "";
    }
  });

  function abortDDG(){
    if(state.ddgAbort){
      try{ state.ddgAbort.abort(); }catch(e){}
      state.ddgAbort = null;
    }
  }

  function ddgSearchLink(q){
    return "https://duckduckgo.com/?q=" + encodeURIComponent(q);
  }

  function escapeHTML(s){
    return String(s || "").replace(/[&<>"']/g, (m) => ({
      "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"
    }[m]));
  }

  async function renderDDG(q){
    ddgPanel.style.display = "block";
    ddgList.innerHTML = "";
    ddgNote.textContent = "";
    ddgStatus.textContent = "Loading...";
    ddgIntro.innerHTML = `Searching externally for <span style="color:rgba(255,255,255,.92);font-weight:720;">${escapeHTML(q)}</span>.`;

    abortDDG();
    const ac = new AbortController();
    state.ddgAbort = ac;

    try{
      const res = await fetch(API.ddg(q), { signal: ac.signal, cache:"no-store" });
      if(!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();

      const items = Array.isArray(data.results) ? data.results : [];
      if(items.length){
        for(const it of items.slice(0,10)){
          const d = document.createElement("div");
          d.className = "ddg-item";

          const a = document.createElement("a");
          a.href = it.url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = (it.title || "").slice(0, 140) || it.url;

          const t = document.createElement("div");
          t.className = "t";
          t.appendChild(a);

          const s = document.createElement("div");
          s.className = "s";
          s.textContent = it.snippet || "";

          d.appendChild(t);
          d.appendChild(s);
          ddgList.appendChild(d);
        }
        ddgStatus.textContent = `${Math.min(items.length,10)} result${items.length === 1 ? "" : "s"}`;
        ddgNote.innerHTML = `More: <a href="${ddgSearchLink(q)}" target="_blank" rel="noopener noreferrer">open full DuckDuckGo results</a>.`;
      }else{
        ddgStatus.textContent = "No results";
        ddgNote.innerHTML = `Open full results: <a href="${ddgSearchLink(q)}" target="_blank" rel="noopener noreferrer">DuckDuckGo search</a>.`;
      }
    }catch(err){
      if(err && err.name === "AbortError") return;
      ddgStatus.textContent = "Unavailable";
      ddgList.innerHTML = "";
      ddgNote.innerHTML = `Open full results: <a href="${ddgSearchLink(q)}" target="_blank" rel="noopener noreferrer">DuckDuckGo search</a>.`;
    }finally{
      state.ddgAbort = null;
    }
  }

  async function boot(){
    await initData();
    renderTree();
    renderCards();
  }

  boot();
})();