# Radar TCG

Agregador de notícias e conteúdo TCG para curadoria editorial do CC Master.

A ideia é simples:

1. buscar notícias em vários idiomas;
2. identificar o TCG;
3. marcar fontes oficiais;
4. remover duplicatas simples;
5. exibir tudo em um painel;
6. permitir marcar localmente o que é **Interessante** ou **Ignorar**;
7. exportar as selecionadas para a etapa editorial do CC Master.

## Jogos monitorados

- Flesh and Blood
- Magic: The Gathering
- Pokémon TCG
- Sorcery: Contested Realm
- Naruto Card Game
- One Piece Card Game
- Star Wars: Unlimited
- Riftbound
- Digimon Card Game
- Yu-Gi-Oh!
- Disney Lorcana
- Novos TCGs / novidades

## Idiomas

- Português
- Inglês
- Espanhol
- Francês
- Japonês
- Chinês simplificado

## Como funciona a primeira versão

A V1 usa feeds de pesquisa do Google News como camada de descoberta global. Isso evita depender de scraping específico para dezenas de sites logo no início.

O coletor também conhece os domínios oficiais dos jogos. Quando uma notícia vem de um deles, ela recebe a marca `official: true`.

Importante: a V1 armazena metadados, título, pequeno trecho fornecido pelo feed e link. Ela **não copia a matéria completa**.

## Estrutura

```text
.
├── .github/workflows/update-news.yml
├── config/
│   ├── games.yml
│   ├── locales.yml
│   └── official_domains.yml
├── data/news.json
├── docs/
│   ├── data/news.json
│   ├── index.html
│   ├── app.js
│   └── style.css
├── scripts/
│   └── collect.py
├── requirements.txt
└── README.md
```

## Rodar localmente

```bash
python -m pip install -r requirements.txt
python scripts/collect.py
```

Depois abra `docs/index.html` através de um servidor HTTP local, por exemplo:

```bash
python -m http.server 8000 -d docs
```

e visite `http://localhost:8000`.

## GitHub Actions

O workflow roda automaticamente a cada 3 horas e também pode ser executado manualmente em:

`Actions > Atualizar radar TCG > Run workflow`

Para permitir que o workflow grave o `news.json`, confira:

`Settings > Actions > General > Workflow permissions > Read and write permissions`

## GitHub Pages

Em:

`Settings > Pages`

configure:

- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

## Curadoria

Os botões **Interessante** e **Ignorar** usam `localStorage` do navegador na V1. Isso significa que sua curadoria fica salva naquele navegador, sem precisar de banco de dados ou login.

O botão **Exportar interessantes** gera um JSON apenas com as notícias marcadas. Esse arquivo poderá ser usado depois para gerar posts do CC Master.

Na V2 podemos persistir a curadoria no próprio GitHub ou em um banco simples.

## Próximos passos planejados

- adaptadores diretos para sites oficiais importantes;
- fontes especializadas escolhidas manualmente;
- melhor cobertura da China e Japão;
- agrupamento de várias matérias sobre a mesma notícia;
- tradução opcional para português;
- resumo automático;
- ranking de prioridade editorial;
- integração com o repositório do CC Master;
- geração de rascunho `.md` para uma notícia aprovada.


## Conteúdo editorial ampliado

O Radar não busca apenas notícias. Ele classifica publicações em: **notícias, lore, decks/deck tech, combos/sinergias, meta, regras/rulings, rumores/leaks, especulações/teorias, curiosidades, design/desenvolvimento, mercado e indústria**.

Os três jogos de prioridade editorial são **Flesh and Blood, Pokémon TCG e Magic: The Gathering**. A interface abre por padrão em “Principais jogos”, mas mantém uma segunda linha com **Todos os jogos** para Sorcery, Naruto, One Piece, Star Wars: Unlimited, Riftbound, Digimon, Yu-Gi-Oh!, Disney Lorcana e novos TCGs.

### Fontes independentes

`config/independent_sources.yml` reúne portais gerais e especializados. Cada fonte pode indicar `trust` (`media`, `community`, `rumor`, `archive`), retenção própria e dicas de classificação. A coleta usa páginas diretas quando viável e busca por domínio como fallback para portais mais difíceis de raspar.

### Flesh and Blood

Além das fontes oficiais, o radar passa a acompanhar conteúdo de FaBTCG.gg, Legendary Stories, The Rathe Times (arquivo), AGE, Judge Blog, TCG Times e Grave-Troll Games/FaB 101, permitindo encontrar lore, estratégia, deckbuilding, puzzles, regras, teorias e especulações.
