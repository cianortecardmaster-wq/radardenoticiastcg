const STORAGE_KEY = "tcg-radar-curation-v2";
const PAGE_SIZE = 50;
const CORE_GAMES = new Set(["flesh-and-blood", "pokemon", "magic"]);

const TYPE_LABELS = {
  news: "NOTÍCIA", lore: "LORE", deck: "DECK", combo: "COMBO", meta: "META",
  rules: "REGRAS", rumor: "RUMOR", speculation: "ESPECULAÇÃO", curiosity: "CURIOSIDADE",
  design: "DESIGN", market: "MERCADO", industry: "INDÚSTRIA",
};
const TRUST_LABELS = {
  official: "OFICIAL", media: "IMPRENSA", community: "COMUNIDADE",
  rumor: "RUMOR", archive: "ARQUIVO", market: "MERCADO",
};

let payload = { items: [], generated_at: null };
let curation = loadCuration();
let visibleLimit = PAGE_SIZE;
let gameMode = { scope: "core", game: "" };

const els = {
  list: document.querySelector("#newsList"), template: document.querySelector("#itemTemplate"),
  search: document.querySelector("#searchInput"), contentType: document.querySelector("#contentTypeFilter"),
  language: document.querySelector("#languageFilter"), trust: document.querySelector("#trustFilter"),
  state: document.querySelector("#stateFilter"), stats: document.querySelector("#stats"),
  generated: document.querySelector("#generatedAt"), visible: document.querySelector("#visibleCount"),
  export: document.querySelector("#exportButton"), more: document.querySelector("#showMoreButton"),
  allGamePills: document.querySelector("#allGamePills"),
};

function loadCuration() { try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch { return {}; } }
function saveCuration() { localStorage.setItem(STORAGE_KEY, JSON.stringify(curation)); }
function stateOf(id) { return curation[id] || "pending"; }
function setState(id, state) { if (state === "pending") delete curation[id]; else curation[id] = state; saveCuration(); render(); }

function fmtDate(value) {
  if (!value) return "Data não informada";
  try { return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(new Date(value)); }
  catch { return value; }
}
function normalize(value) { return (value || "").toLocaleLowerCase(); }
function compact(value) { return (value || "").replace(/\s+/g, " ").trim(); }
function trimText(value, max = 620) {
  const text = compact(value); if (text.length <= max) return text;
  const cut = text.slice(0, max); const lastSpace = cut.lastIndexOf(" ");
  return `${cut.slice(0, lastSpace > 400 ? lastSpace : max).trim()}…`;
}

function cleanSummary(item) {
  const title = compact(item.title); let summary = compact(item.excerpt || item.summary || "");
  if (summary.startsWith(title)) summary = compact(summary.slice(title.length));
  if (item.source && summary.endsWith(item.source)) summary = compact(summary.slice(0, -item.source.length));
  if (summary.length >= 45) return trimText(summary);
  return `Publicação de ${item.source || "fonte externa"} sobre “${trimText(title, 180)}”. O coletor não encontrou um resumo confiável nessa página.`;
}

function contentTypesFor(item) {
  if (Array.isArray(item.content_types) && item.content_types.length) return item.content_types;
  const text = normalize(`${item.title || ""} ${item.excerpt || ""}`);
  const rules = {
    lore:["lore","story","história","historia","世界観","剧情"], deck:["deck","decklist","baralho","mazo","デッキ","卡组"],
    combo:["combo","synergy","sinergia","コンボ","连招"], meta:["meta","tier list","tournament","competitive","matchup","torneio","大会"],
    rules:["rules","ruling","judge","regra","regras","ルール","规则"], rumor:["rumor","leak","vazamento","rumeur","リーク","泄露"],
    speculation:["speculation","theory","especulação","teoria","考察","推测"], curiosity:["trivia","curiosity","curiosidade","豆知識","冷知识"],
    design:["design","developer","development","mecânica","デザイン","设计"], market:["price","market","finance","preço","mercado","価格","市场"],
    industry:["industry","distribution","indústria","業界","行业"],
  };
  const found = Object.entries(rules).filter(([, words]) => words.some(w => text.includes(normalize(w)))).map(([type]) => type);
  return found.length ? found : ["news"];
}

function filteredItems() {
  const q = normalize(els.search.value.trim()); const language = els.language.value;
  const state = els.state.value; const type = els.contentType.value; const trust = els.trust.value;
  return payload.items.filter(item => {
    const itemState = stateOf(item.id);
    if (gameMode.game && item.game_id !== gameMode.game) return false;
    if (!gameMode.game && gameMode.scope === "core" && !CORE_GAMES.has(item.game_id)) return false;
    if (language && item.language !== language) return false;
    if (trust && (item.trust || (item.official ? "official" : "media")) !== trust) return false;
    if (type && !contentTypesFor(item).includes(type)) return false;
    if (state !== "all" && itemState !== state) return false;
    if (q) {
      const haystack = normalize([item.title,item.excerpt,item.summary,item.source,item.game,item.language,item.region,...contentTypesFor(item)].join(" "));
      if (!haystack.includes(q)) return false;
    }
    return true;
  }).sort((a,b) => (Date.parse(b.published_at || b.discovered_at || "") || 0) - (Date.parse(a.published_at || a.discovered_at || "") || 0));
}

function badge(text, className="") { const span=document.createElement("span"); span.className=`badge ${className}`.trim(); span.textContent=text; return span; }

function renderStats() {
  const visibleBase = payload.items.filter(x => !gameMode.game ? (gameMode.scope !== "core" || CORE_GAMES.has(x.game_id)) : x.game_id === gameMode.game);
  const interesting = payload.items.filter(x => stateOf(x.id)==="interesting").length;
  const official = visibleBase.filter(x => x.official).length;
  const loreStrategy = visibleBase.filter(x => contentTypesFor(x).some(t => ["lore","deck","combo","speculation","curiosity"].includes(t))).length;
  els.stats.innerHTML = `
    <div class="stat"><strong>${visibleBase.length}</strong><span>conteúdos nesta visão</span></div>
    <div class="stat"><strong>${official}</strong><span>fontes oficiais</span></div>
    <div class="stat"><strong>${loreStrategy}</strong><span>lore, decks, combos e ideias</span></div>
    <div class="stat"><strong>${interesting}</strong><span>marcados como interessantes</span></div>`;
}

function render() {
  renderStats(); const allFiltered=filteredItems(); const items=allFiltered.slice(0,visibleLimit);
  els.visible.textContent = allFiltered.length > items.length ? `Mostrando ${items.length} de ${allFiltered.length} conteúdo(s)` : `${allFiltered.length} conteúdo(s)`;
  els.more.hidden = items.length >= allFiltered.length; els.list.innerHTML="";
  if (!items.length) { els.list.innerHTML='<div class="empty">Nenhum conteúdo com esses filtros.</div>'; return; }
  const fragment=document.createDocumentFragment();
  for (const item of items) {
    const node=els.template.content.cloneNode(true); const article=node.querySelector(".news-item");
    const badges=node.querySelector(".badges"), time=node.querySelector("time"), title=node.querySelector(".title-link"), summary=node.querySelector(".summary");
    const source=node.querySelector(".source"), origin=node.querySelector(".origin"), open=node.querySelector(".link");
    const interesting=node.querySelector(".interesting"), ignore=node.querySelector(".ignore"); const current=stateOf(item.id); article.dataset.state=current;
    badges.appendChild(badge(item.game,"game"));
    for (const t of contentTypesFor(item).slice(0,3)) badges.appendChild(badge(TYPE_LABELS[t] || t, `type type-${t}`));
    const trust=item.trust || (item.official ? "official" : "media"); badges.appendChild(badge(TRUST_LABELS[trust] || trust, `trust trust-${trust}`));
    badges.appendChild(badge((item.language || "?").toUpperCase()));
    time.textContent=fmtDate(item.published_at); time.dateTime=item.published_at || "";
    title.textContent=compact(item.title); title.href=item.url; summary.textContent=cleanSummary(item);
    source.textContent=`Fonte: ${item.source || "não identificada"}`;
    const details=[item.region,item.collector === "official-page" ? "coleta oficial" : item.collector === "independent-page" ? "portal direto" : "agregador"].filter(Boolean).join(" · ");
    origin.textContent=details ? ` · ${details}` : ""; open.href=item.url;
    interesting.classList.toggle("active",current==="interesting"); ignore.classList.toggle("active",current==="ignored");
    interesting.addEventListener("click",()=>setState(item.id,current==="interesting"?"pending":"interesting"));
    ignore.addEventListener("click",()=>setState(item.id,current==="ignored"?"pending":"ignored")); fragment.appendChild(node);
  }
  els.list.appendChild(fragment);
}

function populateOtherGames() {
  const games=[...new Map(payload.items.map(x=>[x.game_id,x.game])).entries()].filter(([id])=>!CORE_GAMES.has(id)).sort((a,b)=>a[1].localeCompare(b[1],"pt-BR"));
  for (const [id,name] of games) { const btn=document.createElement("button"); btn.className="game-pill"; btn.dataset.game=id; btn.textContent=name; els.allGamePills.appendChild(btn); }
}
function setGameSelection(button) {
  document.querySelectorAll(".game-pill").forEach(b=>b.classList.remove("active")); button.classList.add("active");
  gameMode.game=button.dataset.game || ""; gameMode.scope=button.dataset.scope || (CORE_GAMES.has(gameMode.game)?"core":"all"); resetAndRender();
}
function wireGamePills() { document.querySelectorAll(".game-pill").forEach(btn=>btn.addEventListener("click",()=>setGameSelection(btn))); }
function resetAndRender() { visibleLimit=PAGE_SIZE; render(); }

function exportInteresting() {
  const items=payload.items.filter(x=>stateOf(x.id)==="interesting");
  const blob=new Blob([JSON.stringify({exported_at:new Date().toISOString(),count:items.length,items},null,2)],{type:"application/json;charset=utf-8"});
  const url=URL.createObjectURL(blob); const a=document.createElement("a"); a.href=url; a.download=`tcg-radar-interessantes-${new Date().toISOString().slice(0,10)}.json`; a.click(); URL.revokeObjectURL(url);
}

async function init() {
  try {
    const res=await fetch("./data/news.json",{cache:"no-store"}); if(!res.ok) throw new Error(`HTTP ${res.status}`); payload=await res.json();
    populateOtherGames(); wireGamePills();
    els.generated.textContent=payload.generated_at ? `Atualizado: ${fmtDate(payload.generated_at)}` : "Ainda não atualizado.";
    [els.search,els.contentType,els.language,els.trust,els.state].forEach(el=>el.addEventListener("input",resetAndRender));
    els.export.addEventListener("click",exportInteresting); els.more.addEventListener("click",()=>{visibleLimit+=PAGE_SIZE;render();}); render();
  } catch(err) { els.list.innerHTML=`<div class="empty">Não foi possível carregar o radar: ${err.message}</div>`; }
}
init();
