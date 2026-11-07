const $ = (id) => document.getElementById(id);
let data = null;
let activeTab = "tree";
let sortKey = "depth";
let sortDir = 1;

// ---------- Form submit ----------
$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showMessage("Analyzing... JS rendering may take a little while.", false);
  $("results").classList.add("hidden");
  $("go").disabled = true;

  try {
    const res = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: $("url").value,
        max_pages: $("max_pages").value,
        max_depth: $("max_depth").value,
        render_js: $("render_js").checked,
      }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || "Something went wrong");

    data = json;
    $("message").classList.add("hidden");
    $("results").classList.remove("hidden");
    renderAll();
  } catch (err) {
    showMessage(err.message, true);
  } finally {
    $("go").disabled = false;
  }
});

function showMessage(text, isError) {
  const box = $("message");
  box.textContent = text;
  box.className = "message" + (isError ? " error" : "");
}

// ---------- Tabs + search ----------
document.querySelectorAll(".tab").forEach((btn) =>
  btn.addEventListener("click", () => {
    activeTab = btn.dataset.tab;
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
    ["tree", "pages", "broken"].forEach((t) =>
      $("tab-" + t).classList.toggle("hidden", t !== activeTab));
    $("search").classList.toggle("hidden", activeTab === "tree");
    renderAll();
  })
);
$("search").addEventListener("input", renderAll);

function renderAll() {
  if (!data) return;
  renderStats();
  if (activeTab === "tree") renderTree();
  if (activeTab === "pages") renderPages();
  if (activeTab === "broken") renderBroken();
}

// ---------- Helpers ----------
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;   // textContent = safe
  if (className) node.className = className;
  return node;
}

function renderStats() {
  const s = data.stats;
  const items = [
    ["Pages", s.pages_discovered, ""],
    ["Internal links", s.internal_links, ""],
    ["External links", s.external_links, ""],
    ["Broken links", s.broken_links, s.broken_links ? "bad" : ""],
  ];
  $("stats").replaceChildren(...items.map(([label, value, cls]) => {
    const box = el("div", undefined, "stat " + cls);
    box.append(el("b", value), el("span", label));
    return box;
  }));
}

function statusBadge(page) {
  const bad = page.status === null || page.status >= 400;
  return el("span", page.status ?? page.error, "badge" + (bad ? " bad" : ""));
}

// ---------- Sitemap tree ----------
function renderTree() {
  const byUrl = Object.fromEntries(data.pages.map((p) => [p.url, p]));
  const children = {};
  const seen = new Set([data.start_url]);
  const queue = [data.start_url];

  // BFS: har page ka "parent" wo hai jisne use pehli baar link kiya
  while (queue.length) {
    const url = queue.shift();
    children[url] = [];
    for (const link of byUrl[url].internal_links) {
      if (byUrl[link] && !seen.has(link)) {
        seen.add(link);
        children[url].push(link);
        queue.push(link);
      }
    }
  }

  const ul = el("ul", undefined, "tree");
  ul.append(treeNode(data.start_url, byUrl, children));
  $("tab-tree").replaceChildren(ul);
}
function pathOf(url) {
  const path = new URL(url).pathname;
  return path === "/" ? "/ (home)" : path;
}
function treeNode(url, byUrl, children) {
  const page = byUrl[url];
  const li = el("li");
  const summary = el("summary");
  summary.append(
    el("b", pathOf(url)),
    el("span", page.title, "node-url"),
    statusBadge(page),
    el("span", `internal: ${page.internal_count} · external: ${page.external_count}`, "counts")
  );
  if (children[url].length === 0) {
    li.append(el("div", undefined)); // leaf
    li.firstChild.append(...summary.childNodes);
    return li;
  }
  const details = el("details");
  details.open = true;
  details.append(summary);
  const ul = el("ul", undefined, "tree");
  children[url].forEach((c) => ul.append(treeNode(c, byUrl, children)));
  details.append(ul);
  li.append(details);
  return li;
}

// ---------- Pages table (search + sort) ----------
function renderPages() {
  const q = $("search").value.toLowerCase();
  const rows = data.pages
    .filter((p) => (p.title + p.url).toLowerCase().includes(q))
    .sort((a, b) => {
      const x = a[sortKey] ?? "", y = b[sortKey] ?? "";
      return (x > y ? 1 : x < y ? -1 : 0) * sortDir;
    });

  const cols = [["title", "Title"], ["url", "URL"], ["status", "Status"],
                ["depth", "Depth"], ["internal_count", "Internal"], ["external_count", "External"]];
  const table = el("table");
  const head = el("tr");
  cols.forEach(([key, label]) => {
    const th = el("th", label + (sortKey === key ? (sortDir === 1 ? " ▲" : " ▼") : ""));
    th.addEventListener("click", () => {
      sortDir = sortKey === key ? -sortDir : 1;
      sortKey = key;
      renderPages();
    });
    head.append(th);
  });
  table.append(head);

  rows.forEach((p) => {
    const tr = el("tr");
    [p.title, p.url, p.status ?? p.error, p.depth, p.internal_count, p.external_count]
      .forEach((v) => tr.append(el("td", v)));
    table.append(tr);
  });
  $("tab-pages").replaceChildren(table);
}

// ---------- Broken links ----------
function renderBroken() {
  const q = $("search").value.toLowerCase();
  const rows = data.broken_links.filter((b) => (b.url + b.found_on).toLowerCase().includes(q));
  if (rows.length === 0) {
    $("tab-broken").replaceChildren(el("p", "No broken links found 🎉"));
    return;
  }
  const table = el("table");
  const head = el("tr");
  ["URL", "Type", "Status / Reason", "Found on"].forEach((h) => head.append(el("th", h)));
  table.append(head);
  rows.forEach((b) => {
    const tr = el("tr");
    [b.url, b.type, b.status ?? b.reason, b.found_on].forEach((v) => tr.append(el("td", v)));
    table.append(tr);
  });
  $("tab-broken").replaceChildren(table);
}