const STORAGE_KEY = "tcg-radar-curation-v1";

let payload = { items: [], generated_at: null };
let curation = loadCuration();

const els = {
  list: document.querySelector("#newsList"),
  template: document.querySelector("#cardTemplate"),
  search: document.querySelector("#searchInput"),
  game: document.querySelector("#gameFilter"),
  language: document.querySelector("#languageFilter"),
  state: document.querySelector("#stateFilter"),
  official: document.querySelector("#officialOnly"),
  stats: document.querySelector("#stats"),
  generated: document.querySelector("#generatedAt"),
  visible: document.querySelector("#visibleCount"),
  export: document.querySelector("#exportButton"),
};

function loadCuration() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

function saveCuration() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(curation));
}

function stateOf(id) {
  return curation[id] || "pending";
}

function setState(id, state) {
  if (state === "pending") delete curation[id];
  else curation[id] = state;
  saveCuration();
  render();
}

function fmtDate(value) {
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value || "";
  }
}

function normalize(value) {
  return (value || "").toLocaleLowerCase();
}

function filteredItems() {
  const q = normalize(els.search.value.trim());
  const game = els.game.value;
  const language = els.language.value;
  const state = els.state.value;
  const official = els.official.checked;

  return payload.items.filter(item => {
    const itemState = stateOf(item.id);
    if (game && item.game_id !== game) return false;
    if (language && item.language !== language) return false;
    if (official && !item.official) return false;
    if (state !== "all" && itemState !== state) return false;

    if (q) {
      const haystack = normalize([
        item.title,
        item.excerpt,
        item.source,
        item.game,
        item.language,
      ].join(" "));
      if (!haystack.includes(q)) return false;
    }

    return true;
  });
}

function badge(text, className = "") {
  const span = document.createElement("span");
  span.className = `badge ${className}`.trim();
  span.textContent = text;
  return span;
}

function renderStats() {
  const all = payload.items.length;
  const interesting = payload.items.filter(x => stateOf(x.id) === "interesting").length;
  const ignored = payload.items.filter(x => stateOf(x.id) === "ignored").length;
  const official = payload.items.filter(x => x.official).length;

  els.stats.innerHTML = `
    <div class="stat"><strong>${all}</strong><span>no radar</span></div>
    <div class="stat"><strong>${official}</strong><span>fontes oficiais</span></div>
    <div class="stat"><strong>${interesting}</strong><span>interessantes</span></div>
    <div class="stat"><strong>${ignored}</strong><span>ignoradas</span></div>
  `;
}

function render() {
  renderStats();
  const items = filteredItems();
  els.visible.textContent = `${items.length} notícia(s) exibida(s)`;

  els.list.innerHTML = "";

  if (!items.length) {
    els.list.innerHTML = `<div class="empty">Nenhuma notícia com esses filtros.</div>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  for (const item of items) {
    const node = els.template.content.cloneNode(true);
    const card = node.querySelector(".card");
    const badges = node.querySelector(".badges");
    const time = node.querySelector("time");
    const title = node.querySelector("h2");
    const excerpt = node.querySelector(".excerpt");
    const source = node.querySelector(".source");
    const open = node.querySelector(".link");
    const interesting = node.querySelector(".interesting");
    const ignore = node.querySelector(".ignore");

    const current = stateOf(item.id);
    card.dataset.state = current;

    badges.appendChild(badge(item.game, "game"));
    badges.appendChild(badge(item.language));
    if (item.official) badges.appendChild(badge("oficial", "official"));

    time.textContent = fmtDate(item.published_at);
    time.dateTime = item.published_at;
    title.textContent = item.title;

    if (item.excerpt) {
      excerpt.textContent = item.excerpt;
    } else {
      excerpt.remove();
    }

    source.textContent = `Fonte: ${item.source}`;
    open.href = item.url;

    interesting.classList.toggle("active", current === "interesting");
    ignore.classList.toggle("active", current === "ignored");

    interesting.addEventListener("click", () => {
      setState(item.id, current === "interesting" ? "pending" : "interesting");
    });

    ignore.addEventListener("click", () => {
      setState(item.id, current === "ignored" ? "pending" : "ignored");
    });

    fragment.appendChild(node);
  }

  els.list.appendChild(fragment);
}

function populateGames() {
  const games = [...new Map(payload.items.map(x => [x.game_id, x.game])).entries()]
    .sort((a, b) => a[1].localeCompare(b[1], "pt-BR"));

  for (const [id, name] of games) {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = name;
    els.game.appendChild(option);
  }
}

function exportInteresting() {
  const items = payload.items.filter(x => stateOf(x.id) === "interesting");
  const exportPayload = {
    exported_at: new Date().toISOString(),
    count: items.length,
    items,
  };

  const blob = new Blob(
    [JSON.stringify(exportPayload, null, 2)],
    { type: "application/json;charset=utf-8" }
  );

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `tcg-radar-interessantes-${stamp}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function init() {
  try {
    const res = await fetch("./data/news.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    payload = await res.json();

    populateGames();
    els.generated.textContent = payload.generated_at
      ? `Atualizado: ${fmtDate(payload.generated_at)}`
      : "Ainda não atualizado.";

    [els.search, els.game, els.language, els.state, els.official]
      .forEach(el => el.addEventListener("input", render));

    els.export.addEventListener("click", exportInteresting);
    render();
  } catch (err) {
    els.list.innerHTML = `<div class="empty">Não foi possível carregar o radar: ${err.message}</div>`;
  }
}

init();
