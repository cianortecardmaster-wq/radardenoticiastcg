const STORAGE_KEY = "tcg-radar-curation-v1";
const PAGE_SIZE = 50;

let payload = { items: [], generated_at: null };
let curation = loadCuration();
let visibleLimit = PAGE_SIZE;

const els = {
  list: document.querySelector("#newsList"),
  template: document.querySelector("#itemTemplate"),
  search: document.querySelector("#searchInput"),
  game: document.querySelector("#gameFilter"),
  language: document.querySelector("#languageFilter"),
  state: document.querySelector("#stateFilter"),
  official: document.querySelector("#officialOnly"),
  stats: document.querySelector("#stats"),
  generated: document.querySelector("#generatedAt"),
  visible: document.querySelector("#visibleCount"),
  export: document.querySelector("#exportButton"),
  more: document.querySelector("#showMoreButton"),
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
  if (!value) return "Data não informada";
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function normalize(value) {
  return (value || "").toLocaleLowerCase();
}

function compact(value) {
  return (value || "").replace(/\s+/g, " ").trim();
}

function trimText(value, max = 520) {
  const text = compact(value);
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const lastSpace = cut.lastIndexOf(" ");
  return `${cut.slice(0, lastSpace > 350 ? lastSpace : max).trim()}…`;
}

function cleanSummary(item) {
  const title = compact(item.title);
  let summary = compact(item.excerpt || item.summary || "");

  if (summary) {
    // Alguns feeds repetem título e fonte dentro da descrição.
    if (summary.startsWith(title)) summary = compact(summary.slice(title.length));
    if (item.source && summary.endsWith(item.source)) {
      summary = compact(summary.slice(0, -item.source.length));
    }
  }

  if (summary.length >= 45) return trimText(summary);

  // Fallback para fontes em que a página de listagem ainda não forneceu descrição.
  // Não inventa informação: deixa claro que o resumo detalhado não foi extraído.
  return `Publicação de ${item.source || "fonte externa"} sobre “${trimText(title, 180)}”. O coletor ainda não conseguiu extrair um resumo mais detalhado desta página.`;
}

function filteredItems() {
  const q = normalize(els.search.value.trim());
  const game = els.game.value;
  const language = els.language.value;
  const state = els.state.value;
  const official = els.official.checked;

  return payload.items
    .filter(item => {
      const itemState = stateOf(item.id);
      if (game && item.game_id !== game) return false;
      if (language && item.language !== language) return false;
      if (official && !item.official) return false;
      if (state !== "all" && itemState !== state) return false;

      if (q) {
        const haystack = normalize([
          item.title,
          item.excerpt,
          item.summary,
          item.source,
          item.game,
          item.language,
          item.region,
        ].join(" "));
        if (!haystack.includes(q)) return false;
      }

      return true;
    })
    .sort((a, b) => {
      const da = Date.parse(a.published_at || "") || 0;
      const db = Date.parse(b.published_at || "") || 0;
      return db - da;
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
    <div class="stat"><strong>${official}</strong><span>de fontes oficiais</span></div>
    <div class="stat"><strong>${interesting}</strong><span>interessantes</span></div>
    <div class="stat"><strong>${ignored}</strong><span>ignoradas</span></div>
  `;
}

function render() {
  renderStats();
  const allFiltered = filteredItems();
  const items = allFiltered.slice(0, visibleLimit);

  els.visible.textContent = allFiltered.length > items.length
    ? `Mostrando ${items.length} de ${allFiltered.length} notícia(s)`
    : `${allFiltered.length} notícia(s)`;

  els.more.hidden = items.length >= allFiltered.length;
  els.list.innerHTML = "";

  if (!items.length) {
    els.list.innerHTML = `<div class="empty">Nenhuma notícia com esses filtros.</div>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  for (const item of items) {
    const node = els.template.content.cloneNode(true);
    const article = node.querySelector(".news-item");
    const badges = node.querySelector(".badges");
    const time = node.querySelector("time");
    const title = node.querySelector(".title-link");
    const summary = node.querySelector(".summary");
    const source = node.querySelector(".source");
    const origin = node.querySelector(".origin");
    const open = node.querySelector(".link");
    const interesting = node.querySelector(".interesting");
    const ignore = node.querySelector(".ignore");

    const current = stateOf(item.id);
    article.dataset.state = current;

    badges.appendChild(badge(item.game, "game"));
    badges.appendChild(badge((item.language || "?").toUpperCase()));
    if (item.official) badges.appendChild(badge("OFICIAL", "official"));

    time.textContent = fmtDate(item.published_at);
    time.dateTime = item.published_at || "";

    title.textContent = compact(item.title);
    title.href = item.url;
    summary.textContent = cleanSummary(item);

    source.textContent = `Fonte: ${item.source || "não identificada"}`;
    const details = [item.region, item.collector === "official-page" ? "coleta direta" : "agregador"]
      .filter(Boolean)
      .join(" · ");
    origin.textContent = details ? ` · ${details}` : "";

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

function resetAndRender() {
  visibleLimit = PAGE_SIZE;
  render();
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
      .forEach(el => el.addEventListener("input", resetAndRender));

    els.export.addEventListener("click", exportInteresting);
    els.more.addEventListener("click", () => {
      visibleLimit += PAGE_SIZE;
      render();
    });

    render();
  } catch (err) {
    els.list.innerHTML = `<div class="empty">Não foi possível carregar o radar: ${err.message}</div>`;
  }
}

init();
