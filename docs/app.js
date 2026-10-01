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
const PLATFORM_LABELS = {
  youtube:"YouTube", twitch:"Twitch", podcast:"Podcast", artstation:"ArtStation",
  instagram:"Instagram", x:"X", bluesky:"Bluesky", behance:"Behance", cara:"Cara",
  metafy:"Metafy", patreon:"Patreon", tcgplayer:"TCGplayer", website:"Site / Linktree",
  linkedin:"LinkedIn", facebook:"Facebook", tiktok:"TikTok", discord:"Discord",
  vgen:"VGen", inprnt:"InPrnt", pinterest:"Pinterest", pixiv:"Pixiv", weibo:"Weibo",
  bilibili:"Bilibili", xiaohongshu:"Xiaohongshu", vk:"VK", deviantart:"DeviantArt"
};

let payload = { items: [], generated_at: null };
let mediaPayload = { sources: [], generated_at: null, active_count: 0, content_count: 0, content_ready: false };
let peoplePayload = { people: [], generated_at: null, active_count: 0, content_count: 0, content_ready: false };
let peopleMode = "artdev";
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
  mediaPlatform: document.querySelector("#mediaPlatformFilter"), mediaLanguage: document.querySelector("#mediaLanguageFilter"), mediaActivity: document.querySelector("#mediaActivityFilter"), mediaCount: document.querySelector("#mediaCount"),
  peopleView: document.querySelector("#peopleView"), peopleList: document.querySelector("#peopleList"),
  peopleSearch: document.querySelector("#peopleSearchInput"), peopleGame: document.querySelector("#peopleGameFilter"),
  peopleRole: document.querySelector("#peopleRoleFilter"), peoplePlatform: document.querySelector("#peoplePlatformFilter"),
  peopleActivity: document.querySelector("#peopleActivityFilter"), peopleCount: document.querySelector("#peopleCount"),
  peopleEyebrow: document.querySelector("#peopleEyebrow"), peopleTitle: document.querySelector("#peopleTitle"),
  peopleDescription: document.querySelector("#peopleDescription"),
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

function mediaRecentItems(item) {
  return (item.recent_items || [])
    .filter(entry => isWithinWindow(entry.published_at))
    .sort((a,b) => (Date.parse(b.published_at || "") || 0) - (Date.parse(a.published_at || "") || 0));
}

function mediaFiltered() {
  const q=normalize(els.mediaSearch.value.trim()); const game=els.mediaGame.value; const platform=els.mediaPlatform.value; const language=els.mediaLanguage.value;
  const activity=els.mediaActivity ? els.mediaActivity.value : "recent";
  return (mediaPayload.sources || []).filter(item => {
    const recent=mediaRecentItems(item);
    if (game && item.game_id !== game) return false;
    if (platform && item.platform !== platform) return false;
    if (language && item.language !== language) return false;
    if (activity === "recent" && mediaPayload.content_ready !== false && !recent.length) return false;
    if (q) {
      const haystack=normalize([item.name,item.platform,item.language,...(item.focus || []),...recent.flatMap(x=>[x.title,x.author,x.kind])].join(" "));
      if (!haystack.includes(q)) return false;
    }
    return true;
  }).sort((a,b) => {
    const aLatest=Date.parse(mediaRecentItems(a)[0]?.published_at || "") || 0;
    const bLatest=Date.parse(mediaRecentItems(b)[0]?.published_at || "") || 0;
    return (bLatest-aLatest) || a.name.localeCompare(b.name,"pt-BR");
  });
}

function mediaKindLabel(item, source) {
  if (item.kind === "episode") return "Episódio";
  if (item.kind === "vod") return "VOD";
  if (item.content_platform === "youtube" || source.platform === "youtube") return "Vídeo";
  return "Conteúdo";
}

function renderMedia() {
  const items=mediaFiltered(); els.mediaList.innerHTML="";
  const allSources=mediaPayload.sources || [];
  const allRecent=allSources.flatMap(mediaRecentItems);
  const active=allSources.filter(item=>mediaRecentItems(item).length).length;
  els.mediaCount.textContent=`${items.length} exibidos · ${active} canais ativos · ${allRecent.length} conteúdos / 7 dias`;
  if (!items.length) {
    const msg = mediaPayload.content_ready === false
      ? "A coleta de vídeos e podcasts ainda não rodou. Execute o workflow para preencher os conteúdos atuais."
      : "Nenhum canal publicou conteúdo nos últimos 7 dias com esses filtros.";
    els.mediaList.innerHTML=`<div class="empty media-empty">${msg}</div>`;
    return;
  }
  const frag=document.createDocumentFragment();
  for (const item of items) {
    const recent=mediaRecentItems(item);
    const card=document.createElement("article"); card.className=`media-card platform-${item.platform || "other"}`;
    const top=document.createElement("div"); top.className="media-card-top";
    const platform=document.createElement("span"); platform.className="media-platform"; platform.textContent=PLATFORM_LABELS[item.platform] || item.platform || "Canal";
    const lang=document.createElement("span"); lang.className="media-lang"; lang.textContent=(item.language || "?").toUpperCase();
    top.append(platform,lang);
    const game=document.createElement("span"); game.className="media-game"; game.textContent=item.game_id === "magic" ? "MAGIC" : "FAB";
    const title=document.createElement("h3"); title.textContent=item.name;
    const focus=document.createElement("div"); focus.className="media-focus"; focus.appendChild(badge(game.textContent,"media-game-badge"));
    for (const tag of item.focus || []) focus.appendChild(badge(tag,"media-tag"));

    const recentWrap=document.createElement("div"); recentWrap.className="media-recent";
    const recentHead=document.createElement("div"); recentHead.className="media-recent-head";
    const recentTitle=document.createElement("strong"); recentTitle.textContent=recent.length ? `${recent.length} publicação${recent.length===1?"":"ões"} nos últimos 7 dias` : "Sem publicação nos últimos 7 dias";
    recentHead.appendChild(recentTitle); recentWrap.appendChild(recentHead);

    if (recent.length) {
      const list=document.createElement("div"); list.className="media-recent-list";
      for (const entry of recent) {
        const row=document.createElement("a"); row.className="media-recent-item"; row.href=entry.url; row.target="_blank"; row.rel="noopener noreferrer";
        if (entry.image_url) {
          const img=document.createElement("img"); img.src=entry.image_url; img.alt=""; img.loading="lazy"; row.appendChild(img);
        } else {
          const placeholder=document.createElement("span"); placeholder.className="media-thumb-placeholder"; placeholder.textContent=item.platform === "podcast" ? "POD" : item.platform === "twitch" ? "LIVE" : "▶"; row.appendChild(placeholder);
        }
        const body=document.createElement("span"); body.className="media-recent-body";
        const entryTitle=document.createElement("span"); entryTitle.className="media-recent-title"; entryTitle.textContent=entry.title;
        const meta=document.createElement("span"); meta.className="media-recent-meta"; meta.textContent=`${mediaKindLabel(entry,item)} · ${fmtDate(entry.published_at)}`;
        body.append(entryTitle,meta); row.appendChild(body); list.appendChild(row);
      }
      recentWrap.appendChild(list);
    }

    const link=document.createElement("a"); link.className="button media-link"; link.href=item.resolved_url || item.url; link.target="_blank"; link.rel="noopener noreferrer";
    link.textContent=item.platform === "podcast" ? "Abrir podcast / canal" : item.platform === "twitch" ? "Abrir Twitch" : "Abrir canal";
    card.append(top,title,focus,recentWrap,link); frag.appendChild(card);
  }
  els.mediaList.appendChild(frag);
}


function gameLabel(game) {
  if (game === "magic") return "MAGIC";
  if (game === "flesh-and-blood") return "FAB";
  if (game === "pokemon") return "POKÉMON";
  return (game || "").toUpperCase();
}

function peopleRecentItems(item) {
  return (item.recent_items || [])
    .filter(entry => isWithinWindow(entry.published_at))
    .sort((a,b) => (Date.parse(b.published_at || "") || 0) - (Date.parse(a.published_at || "") || 0));
}

function configurePeopleView(mode) {
  peopleMode=mode;
  const artdev=mode === "artdev";
  els.peopleEyebrow.textContent=artdev ? "FLESH AND BLOOD" : "FLESH AND BLOOD + MAGIC";
  els.peopleTitle.textContent=artdev ? "Artistas & desenvolvedores" : "Pro players";
  els.peopleDescription.textContent=artdev
    ? "Perfis públicos, portfólios e publicações recentes de artistas, diretores e desenvolvedores ligados a Flesh and Blood."
    : "Jogadores de alto nível com produção pública: vídeos, podcasts, streams, artigos, guias, Patreon e Metafy.";

  const previous=els.peopleRole.value;
  const roles=artdev
    ? [["","Todas as funções"],["artista","Artistas"],["desenvolv","Desenvolvimento / LSS"],["direção","Direção criativa"]]
    : [["","Todas as funções"],["pro player","Pro players"],["autor","Autores / guias"],["podcast","Podcasts"],["youtube","YouTube / Twitch"],["coach","Coaching"]];
  els.peopleRole.innerHTML="";
  for (const [value,label] of roles) {
    const option=document.createElement("option"); option.value=value; option.textContent=label; els.peopleRole.appendChild(option);
  }
  if ([...els.peopleRole.options].some(o=>o.value===previous)) els.peopleRole.value=previous;
}

function peopleFiltered() {
  const category=peopleMode === "artdev" ? "artist-developer" : "pro-player";
  const q=normalize(els.peopleSearch.value.trim());
  const game=els.peopleGame.value;
  const role=normalize(els.peopleRole.value);
  const platform=els.peoplePlatform.value;
  const activity=els.peopleActivity.value;

  return (peoplePayload.people || []).filter(item => {
    if (item.category !== category) return false;
    const recent=peopleRecentItems(item);
    const profiles=item.profiles || [];
    if (game && !(item.games || []).includes(game)) return false;
    if (role && !normalize((item.roles || []).join(" ")).includes(role) && !normalize(item.description || "").includes(role)) return false;
    if (platform) {
      const hasProfile=profiles.some(p=>p.platform===platform);
      const hasRecent=recent.some(entry=>(entry.content_platform || entry.source_platform)===platform);
      if (!hasProfile && !hasRecent) return false;
    }
    if (activity === "recent" && peoplePayload.content_ready !== false && !recent.length) return false;
    if (q) {
      const haystack=normalize([
        item.name,item.description,...(item.roles || []),...(item.games || []),
        ...profiles.flatMap(p=>[p.label,p.platform]),
        ...recent.flatMap(entry=>[entry.title,entry.author,entry.kind,entry.source_name,entry.content_platform])
      ].join(" "));
      if (!haystack.includes(q)) return false;
    }
    return true;
  }).sort((a,b) => {
    const aLatest=Date.parse(peopleRecentItems(a)[0]?.published_at || "") || 0;
    const bLatest=Date.parse(peopleRecentItems(b)[0]?.published_at || "") || 0;
    return (bLatest-aLatest) || a.name.localeCompare(b.name,"pt-BR");
  });
}

function personRecentKindLabel(entry) {
  if (entry.kind === "artwork" || entry.content_platform === "artstation") return "Arte";
  if (entry.kind === "episode") return "Episódio";
  if (entry.kind === "vod") return "VOD";
  if (entry.content_platform === "youtube") return "Vídeo";
  return "Conteúdo";
}

function renderPeople() {
  const items=peopleFiltered();
  els.peopleList.innerHTML="";
  const category=peopleMode === "artdev" ? "artist-developer" : "pro-player";
  const all=(peoplePayload.people || []).filter(item=>item.category===category);
  const active=all.filter(item=>peopleRecentItems(item).length).length;
  const recentCount=all.reduce((sum,item)=>sum+peopleRecentItems(item).length,0);
  els.peopleCount.textContent=`${items.length} exibidos · ${active} com conteúdo recente · ${recentCount} conteúdos / 7 dias`;

  if (!items.length) {
    const msg=peoplePayload.content_ready === false
      ? "O diretório está pronto, mas a primeira coleta de conteúdo ainda não rodou."
      : "Nenhum perfil corresponde aos filtros selecionados.";
    els.peopleList.innerHTML=`<div class="empty media-empty">${msg}</div>`;
    return;
  }

  const frag=document.createDocumentFragment();
  for (const item of items) {
    const recent=peopleRecentItems(item);
    const card=document.createElement("article"); card.className="media-card people-card";

    const top=document.createElement("div"); top.className="media-card-top";
    const kind=document.createElement("span"); kind.className="media-platform";
    kind.textContent=peopleMode === "artdev" ? ((item.roles || []).some(r=>normalize(r).includes("desenvolv")) ? "ARTISTA / DESENVOLVIMENTO" : "ARTISTA") : "PRO PLAYER";
    const activity=document.createElement("span"); activity.className="media-lang";
    activity.textContent=recent.length ? `${recent.length} RECENTE${recent.length===1?"":"S"}` : "PERFIL";
    top.append(kind,activity);

    const title=document.createElement("h3"); title.textContent=item.name;
    const focus=document.createElement("div"); focus.className="media-focus";
    for (const game of item.games || []) focus.appendChild(badge(gameLabel(game),"media-game-badge"));
    for (const roleName of (item.roles || []).slice(0,3)) focus.appendChild(badge(roleName,"media-tag"));

    if (item.description) {
      const desc=document.createElement("p"); desc.className="people-description"; desc.textContent=item.description;
      card.append(top,title,focus,desc);
    } else {
      card.append(top,title,focus);
    }

    const profiles=item.profiles || [];
    if (profiles.length) {
      const links=document.createElement("div"); links.className="people-links";
      for (const profile of profiles) {
        const a=document.createElement("a"); a.className=`people-link profile-${profile.platform || "other"}`;
        a.href=profile.url; a.target="_blank"; a.rel="noopener noreferrer";
        a.textContent=profile.label || PLATFORM_LABELS[profile.platform] || profile.platform;
        links.appendChild(a);
      }
      card.appendChild(links);
    } else {
      const noProfiles=document.createElement("p"); noProfiles.className="people-no-profiles";
      noProfiles.textContent="Nenhum perfil público confirmado no diretório.";
      card.appendChild(noProfiles);
    }

    const recentWrap=document.createElement("div"); recentWrap.className="media-recent";
    const recentHead=document.createElement("div"); recentHead.className="media-recent-head";
    const recentTitle=document.createElement("strong");
    recentTitle.textContent=recent.length ? `${recent.length} publicação${recent.length===1?"":"ões"} coletada${recent.length===1?"":"s"} nos últimos 7 dias` : "Sem conteúdo coletável nos últimos 7 dias";
    recentHead.appendChild(recentTitle); recentWrap.appendChild(recentHead);

    if (recent.length) {
      const list=document.createElement("div"); list.className="media-recent-list";
      for (const entry of recent) {
        const row=document.createElement("a"); row.className="media-recent-item"; row.href=entry.url; row.target="_blank"; row.rel="noopener noreferrer";
        if (entry.image_url) {
          const img=document.createElement("img"); img.src=entry.image_url; img.alt=""; img.loading="lazy"; row.appendChild(img);
        } else {
          const placeholder=document.createElement("span"); placeholder.className="media-thumb-placeholder";
          placeholder.textContent=entry.content_platform === "artstation" ? "ART" : entry.content_platform === "twitch" ? "LIVE" : entry.kind === "episode" ? "POD" : "▶";
          row.appendChild(placeholder);
        }
        const body=document.createElement("span"); body.className="media-recent-body";
        const entryTitle=document.createElement("span"); entryTitle.className="media-recent-title"; entryTitle.textContent=entry.title;
        const meta=document.createElement("span"); meta.className="media-recent-meta";
        const source=PLATFORM_LABELS[entry.content_platform || entry.source_platform] || entry.source_name || "";
        meta.textContent=[personRecentKindLabel(entry),source,fmtDate(entry.published_at)].filter(Boolean).join(" · ");
        body.append(entryTitle,meta); row.appendChild(body); list.appendChild(row);
      }
      recentWrap.appendChild(list);
    }
    card.appendChild(recentWrap);
    frag.appendChild(card);
  }
  els.peopleList.appendChild(frag);
}

function setView(view) {
  const media=view === "media";
  const people=view === "artdev" || view === "proplayers";
  els.newsView.hidden=media || people;
  els.mediaView.hidden=!media;
  els.peopleView.hidden=!people;
  els.export.hidden=media || people;
  document.querySelectorAll(".view-tab").forEach(btn=>btn.classList.toggle("active",btn.dataset.view===view));
  if (media) renderMedia();
  if (people) {
    configurePeopleView(view);
    renderPeople();
  }
}

async function fetchJson(url, fallback) {
  try { const res=await fetch(url,{cache:"no-store"}); if(!res.ok) throw new Error(`HTTP ${res.status}`); return await res.json(); }
  catch { return fallback; }
}

async function init() {
  const [news,media,people]=await Promise.all([
    fetchJson("./data/news.json", {items:[],generated_at:null}),
    fetchJson("./data/media.json", {sources:[],generated_at:null,content_ready:false}),
    fetchJson("./data/people.json", {people:[],generated_at:null,content_ready:false}),
  ]);
  payload=news; mediaPayload=media; peoplePayload=people;
  populateOtherGames(); wireGamePills(); configurePeopleView("artdev");
  els.generated.textContent=payload.generated_at ? `Atualizado: ${fmtDate(payload.generated_at,true)} · janela: 7 dias · coleta: 3h` : "Ainda não atualizado.";
  [els.search,els.contentType,els.language,els.trust,els.sort,els.state].forEach(el=>el.addEventListener("input",resetAndRender));
  [els.mediaSearch,els.mediaGame,els.mediaPlatform,els.mediaLanguage,els.mediaActivity].filter(Boolean).forEach(el=>el.addEventListener("input",renderMedia));
  [els.peopleSearch,els.peopleGame,els.peopleRole,els.peoplePlatform,els.peopleActivity].filter(Boolean).forEach(el=>el.addEventListener("input",renderPeople));
  document.querySelectorAll(".view-tab").forEach(btn=>btn.addEventListener("click",()=>setView(btn.dataset.view)));
  els.export.addEventListener("click",exportInteresting); els.more.addEventListener("click",()=>{visibleLimit+=PAGE_SIZE;render();});
  render(); renderMedia(); renderPeople();
}
init();
