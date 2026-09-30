const STORAGE_KEY = "tcg-radar-curation-v3";
const PAGE_SIZE = 50;
const DISPLAY_DAYS = 7;
const CORE_GAMES = new Set(["flesh-and-blood", "pokemon", "magic"]);

const TYPE_LABELS = {
  art: "ARTE", meme: "MEME", play: "JOGADA", discussion: "DISCUSSÃO", video: "VÍDEO", community: "COMUNIDADE",
  news: "NOTÍCIA", lore: "LORE", deck: "DECK", combo: "COMBO", meta: "META",
  rules: "REGRAS", rumor: "RUMOR", speculation: "ESPECULAÇÃO", curiosity: "CURIOSIDADE",
  design: "DESIGN", market: "MERCADO", industry: "INDÚSTRIA",
};
const TRUST_LABELS = {
  official: "OFICIAL", media: "IMPRENSA", community: "COMUNIDADE",
  rumor: "RUMOR", archive: "ARQUIVO", market: "MERCADO",
};
const PLATFORM_LABELS = { youtube: "YouTube", twitch: "Twitch", podcast: "Podcast" };

let payload = { items: [], generated_at: null };
let mediaPayload = { sources: [], generated_at: null };
let curation = loadCuration();
let visibleLimit = PAGE_SIZE;
let gameMode = { scope: "core", game: "" };

const els = {
  list: document.querySelector("#newsList"), template: document.querySelector("#itemTemplate"),
  search: document.querySelector("#searchInput"), contentType: document.querySelector("#contentTypeFilter"),
  language: document.querySelector("#languageFilter"), trust: document.querySelector("#trustFilter"),
  sort: document.querySelector("#sortFilter"), state: document.querySelector("#stateFilter"), stats: document.querySelector("#stats"),
  generated: document.querySelector("#generatedAt"), visible: document.querySelector("#visibleCount"),
  export: document.querySelector("#exportButton"), more: document.querySelector("#showMoreButton"),
  allGamePills: document.querySelector("#allGamePills"), newsView: document.querySelector("#newsView"),
  mediaView: document.querySelector("#mediaView"), mediaList: document.querySelector("#mediaList"),
  mediaSearch: document.querySelector("#mediaSearchInput"), mediaGame: document.querySelector("#mediaGameFilter"),
  mediaPlatform: document.querySelector("#mediaPlatformFilter"), mediaLanguage: document.querySelector("#mediaLanguageFilter"), mediaCount: document.querySelector("#mediaCount"),
};

function loadCuration() { try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch { return {}; } }
function saveCuration() { localStorage.setItem(STORAGE_KEY, JSON.stringify(curation)); }
function stateOf(id) { return curation[id] || "pending"; }
function setState(id, state) { if (state === "pending") delete curation[id]; else curation[id] = state; saveCuration(); render(); }

function fmtDate(value, withTime = false) {
  if (!value) return "Data não informada";
  try {
    const options = withTime ? { dateStyle: "short", timeStyle: "short" } : { dateStyle: "short" };
    return new Intl.DateTimeFormat("pt-BR", options).format(new Date(value));
  } catch { return value; }
}
function normalize(value) { return (value || "").toLocaleLowerCase(); }
function compact(value) { return (value || "").replace(/\s+/g, " ").trim(); }
function trimText(value, max = 620) {
  const text = compact(value); if (text.length <= max) return text;
  const cut = text.slice(0, max); const lastSpace = cut.lastIndexOf(" ");
  return `${cut.slice(0, lastSpace > 400 ? lastSpace : max).trim()}…`;
}
function isWithinWindow(value) {
  if (!value) return false;
  const stamp = Date.parse(value);
  if (!Number.isFinite(stamp)) return false;
  const now = Date.now();
  const oldest = now - DISPLAY_DAYS * 24 * 60 * 60 * 1000;
  const futureTolerance = now + 6 * 60 * 60 * 1000;
  return stamp >= oldest && stamp <= futureTolerance;
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
    art:["fan art","fanart","artwork","illustration","alter","painted","painting","playmat","cosplay","arte","ilustração"],
    meme:["meme","humor","funny","joke","shitpost","circlejerk","comedy","piada","engraçado"],
    play:["gameplay","crazy play","misplay","lethal","damage","how would you play","jogada","partida"],
    discussion:["discussion","question","thoughts","what do you think","hot take","opinion","opinião","discussão"],
    video:["video","clip","youtube","twitch","stream","shorts","reel","vídeo","clipe"],
    community:["community","armory","local game store","lgs","meetup","fan friday","content creator","creator spotlight","comunidade"],
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

function recentItems() { return payload.items.filter(item => isWithinWindow(item.published_at)); }

function filteredItems() {
  const q = normalize(els.search.value.trim()); const language = els.language.value;
  const state = els.state.value; const type = els.contentType.value; const trust = els.trust.value; const sort = els.sort.value;
  const filtered = recentItems().filter(item => {
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
  });
  if (sort === "circulating") {
    return filtered.sort((a,b) => ((b.engagement_score || 0) - (a.engagement_score || 0)) || ((Date.parse(b.published_at || "") || 0) - (Date.parse(a.published_at || "") || 0)));
  }
  return filtered.sort((a,b) => (Date.parse(b.published_at || "") || 0) - (Date.parse(a.published_at || "") || 0));
}

function badge(text, className="") { const span=document.createElement("span"); span.className=`badge ${className}`.trim(); span.textContent=text; return span; }

function renderStats() {
  const base = recentItems();
  const visibleBase = base.filter(x => !gameMode.game ? (gameMode.scope !== "core" || CORE_GAMES.has(x.game_id)) : x.game_id === gameMode.game);
  const interesting = base.filter(x => stateOf(x.id)==="interesting").length;
  const social = visibleBase.filter(x => contentTypesFor(x).some(t => ["art","meme","play","discussion","video","community"].includes(t))).length;
  const ideaContent = visibleBase.filter(x => contentTypesFor(x).some(t => ["art","meme","play","discussion","video","community","lore","curiosity"].includes(t))).length;
  els.stats.innerHTML = `
    <div class="stat"><strong>${visibleBase.length}</strong><span>conteúdos dos últimos 7 dias</span></div>
    <div class="stat"><strong>${social}</strong><span>arte, memes, jogadas e comunidade</span></div>
    <div class="stat"><strong>${ideaContent}</strong><span>itens úteis para curadoria</span></div>
    <div class="stat"><strong>${interesting}</strong><span>salvos para usar depois</span></div>`;
}

function render() {
  renderStats(); const allFiltered=filteredItems(); const items=allFiltered.slice(0,visibleLimit);
  els.visible.textContent = allFiltered.length > items.length ? `Mostrando ${items.length} de ${allFiltered.length} conteúdo(s)` : `${allFiltered.length} conteúdo(s)`;
  els.more.hidden = items.length >= allFiltered.length; els.list.innerHTML="";
  if (!items.length) { els.list.innerHTML='<div class="empty">Nenhum conteúdo publicado nos últimos 7 dias com esses filtros.</div>'; return; }
  const fragment=document.createDocumentFragment();
  for (const item of items) {
    const node=els.template.content.cloneNode(true); const article=node.querySelector(".news-item");
    const preview=node.querySelector(".preview-link"), previewImage=node.querySelector(".preview-image");
    const badges=node.querySelector(".badges"), time=node.querySelector("time"), title=node.querySelector(".title-link"), summary=node.querySelector(".summary");
    const source=node.querySelector(".source"), origin=node.querySelector(".origin"), open=node.querySelector(".link");
    const interesting=node.querySelector(".interesting"), ignore=node.querySelector(".ignore"); const current=stateOf(item.id); article.dataset.state=current;
    badges.appendChild(badge(item.game,"game"));
    for (const t of contentTypesFor(item).slice(0,3)) badges.appendChild(badge(TYPE_LABELS[t] || t, `type type-${t}`));
    const trust=item.trust || (item.official ? "official" : "media"); badges.appendChild(badge(TRUST_LABELS[trust] || trust, `trust trust-${trust}`));
    badges.appendChild(badge((item.language || "?").toUpperCase()));
    time.textContent=fmtDate(item.published_at); time.dateTime=item.published_at || "";
    title.textContent=compact(item.title); title.href=item.url; summary.textContent=cleanSummary(item);
    if (item.image_url) { preview.hidden=false; preview.href=item.url; previewImage.src=item.image_url; previewImage.alt=`Prévia de ${compact(item.title)}`; article.classList.add("has-preview"); }
    source.textContent=`Fonte: ${item.source || "não identificada"}`;
    const engagement = ["reddit-json","reddit-rss"].includes(item.collector) && ((item.score || 0) || (item.num_comments || 0)) ? [`↑ ${item.score || 0}`, `${item.num_comments || 0} comentários`] : [];
    const collectorLabel=item.collector === "official-page" ? "coleta oficial" : item.collector === "independent-page" ? "portal direto" : item.collector === "independent-search" ? "busca por fonte" : ["reddit-json","reddit-rss"].includes(item.collector) ? "comunidade / Reddit" : "agregador";
    const details=[...engagement,item.reddit_flair,item.region,collectorLabel].filter(Boolean).join(" · ");
    origin.textContent=details ? ` · ${details}` : ""; open.href=item.url;
    interesting.classList.toggle("active",current==="interesting"); ignore.classList.toggle("active",current==="ignored");
    interesting.addEventListener("click",()=>setState(item.id,current==="interesting"?"pending":"interesting"));
    ignore.addEventListener("click",()=>setState(item.id,current==="ignored"?"pending":"ignored")); fragment.appendChild(node);
  }
  els.list.appendChild(fragment);
}

function populateOtherGames() {
  const games=[...new Map(recentItems().map(x=>[x.game_id,x.game])).entries()].filter(([id])=>!CORE_GAMES.has(id)).sort((a,b)=>a[1].localeCompare(b[1],"pt-BR"));
  for (const [id,name] of games) { const btn=document.createElement("button"); btn.className="game-pill"; btn.dataset.game=id; btn.textContent=name; els.allGamePills.appendChild(btn); }
}
function setGameSelection(button) {
  document.querySelectorAll(".game-pill").forEach(b=>b.classList.remove("active")); button.classList.add("active");
  gameMode.game=button.dataset.game || ""; gameMode.scope=button.dataset.scope || (CORE_GAMES.has(gameMode.game)?"core":"all"); resetAndRender();
}
function wireGamePills() { document.querySelectorAll(".game-pill").forEach(btn=>btn.addEventListener("click",()=>setGameSelection(btn))); }
function resetAndRender() { visibleLimit=PAGE_SIZE; render(); }

function exportInteresting() {
  const items=recentItems().filter(x=>stateOf(x.id)==="interesting");
  const blob=new Blob([JSON.stringify({exported_at:new Date().toISOString(),window_days:DISPLAY_DAYS,count:items.length,items},null,2)],{type:"application/json;charset=utf-8"});
  const url=URL.createObjectURL(blob); const a=document.createElement("a"); a.href=url; a.download=`tcg-radar-interessantes-${new Date().toISOString().slice(0,10)}.json`; a.click(); URL.revokeObjectURL(url);
}

function mediaFiltered() {
  const q=normalize(els.mediaSearch.value.trim()); const game=els.mediaGame.value; const platform=els.mediaPlatform.value; const language=els.mediaLanguage.value;
  return (mediaPayload.sources || []).filter(item => {
    if (game && item.game_id !== game) return false;
    if (platform && item.platform !== platform) return false;
    if (language && item.language !== language) return false;
    if (q) {
      const haystack=normalize([item.name,item.platform,item.language,...(item.focus || [])].join(" "));
      if (!haystack.includes(q)) return false;
    }
    return true;
  }).sort((a,b)=>a.name.localeCompare(b.name,"pt-BR"));
}

function renderMedia() {
  const items=mediaFiltered(); els.mediaList.innerHTML="";
  els.mediaCount.textContent=`${items.length} de ${(mediaPayload.sources || []).length} fontes`;
  if (!items.length) { els.mediaList.innerHTML='<div class="empty media-empty">Nenhum canal com esses filtros.</div>'; return; }
  const frag=document.createDocumentFragment();
  for (const item of items) {
    const card=document.createElement("article"); card.className=`media-card platform-${item.platform || "other"}`;
    const top=document.createElement("div"); top.className="media-card-top";
    const platform=document.createElement("span"); platform.className="media-platform"; platform.textContent=PLATFORM_LABELS[item.platform] || item.platform || "Canal";
    const lang=document.createElement("span"); lang.className="media-lang"; lang.textContent=(item.language || "?").toUpperCase();
    top.append(platform,lang);
    const game=document.createElement("span"); game.className="media-game"; game.textContent=item.game_id === "magic" ? "MAGIC" : "FAB";
    const title=document.createElement("h3"); title.textContent=item.name;
    const focus=document.createElement("div"); focus.className="media-focus"; focus.appendChild(badge(game.textContent,"media-game-badge"));
    for (const tag of item.focus || []) focus.appendChild(badge(tag,"media-tag"));
    const link=document.createElement("a"); link.className="button media-link"; link.href=item.url; link.target="_blank"; link.rel="noopener noreferrer"; link.textContent=item.platform === "podcast" ? "Abrir podcast" : item.platform === "twitch" ? "Abrir / buscar na Twitch" : "Abrir / buscar no YouTube";
    card.append(top,title,focus,link); frag.appendChild(card);
  }
  els.mediaList.appendChild(frag);
}

function setView(view) {
  const media=view === "media";
  els.newsView.hidden=media; els.mediaView.hidden=!media; els.export.hidden=media;
  document.querySelectorAll(".view-tab").forEach(btn=>btn.classList.toggle("active",btn.dataset.view===view));
  if (media) renderMedia();
}

async function fetchJson(url, fallback) {
  try { const res=await fetch(url,{cache:"no-store"}); if(!res.ok) throw new Error(`HTTP ${res.status}`); return await res.json(); }
  catch { return fallback; }
}

async function init() {
  const [news,media]=await Promise.all([
    fetchJson("./data/news.json", {items:[],generated_at:null}),
    fetchJson("./data/media.json", {sources:[],generated_at:null}),
  ]);
  payload=news; mediaPayload=media;
  populateOtherGames(); wireGamePills();
  els.generated.textContent=payload.generated_at ? `Atualizado: ${fmtDate(payload.generated_at,true)} · janela: 7 dias · coleta: 3h` : "Ainda não atualizado.";
  [els.search,els.contentType,els.language,els.trust,els.sort,els.state].forEach(el=>el.addEventListener("input",resetAndRender));
  [els.mediaSearch,els.mediaGame,els.mediaPlatform,els.mediaLanguage].forEach(el=>el.addEventListener("input",renderMedia));
  document.querySelectorAll(".view-tab").forEach(btn=>btn.addEventListener("click",()=>setView(btn.dataset.view)));
  els.export.addEventListener("click",exportInteresting); els.more.addEventListener("click",()=>{visibleLimit+=PAGE_SIZE;render();});
  render(); renderMedia();
}
init();
