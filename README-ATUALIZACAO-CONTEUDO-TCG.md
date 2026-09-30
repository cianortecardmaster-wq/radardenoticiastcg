# Atualização — agregador de conteúdo TCG

Esta versão amplia o Radar de Notícias para um **Radar TCG de conteúdo**.

## O que entrou

- Separação visual entre **Principais jogos** e **Todos os jogos**.
- Principais jogos: **Flesh and Blood, Pokémon TCG e Magic: The Gathering**.
- Filtros por tipo de conteúdo: notícia, lore, deck, combo, meta, regras, rumor, especulação, curiosidade, design, mercado e indústria.
- Classificação da fonte: oficial, imprensa, comunidade, rumor e arquivo.
- Busca temática extra em 6 idiomas para Flesh and Blood, Pokémon e Magic.
- Novo arquivo `config/independent_sources.yml` com portais gerais e especializados.
- Conteúdo evergreen pode permanecer no radar por mais tempo que notícias comuns.
- Conteúdo sem data só é aceito em fontes explicitamente marcadas como evergreen; nunca recebe a data de hoje artificialmente.

## Fontes independentes iniciais

### Gerais
TCGplayer Content, Card Gamer, ICv2, Wargamer, TCG Rumors e BMJ TCG.

### Flesh and Blood
FaBTCG.gg, Legendary Stories, The Rathe Times (arquivo), AGE, Flesh and Blood Judge Blog, TCG Times e Grave-Troll Games / FaB 101.

### Outros jogos
PokéBeach, PokéGuardian, MTGGoldfish, MTG Rocks, Sorcery Brasil, SorceryRec, OnePiece.gg, YGOrganization, StarWarsUnlimited.gg, Garbage Rollers (arquivo), Riftbound.gg, Digimon Card Meta e Mushu Report.

## Depois de subir no GitHub

Execute:

`Actions > Atualizar radar TCG > Run workflow`

A primeira execução vai preencher `content_types`, `trust`, `game_group` e incorporar as novas fontes. Alguns sites podem bloquear coleta direta; nesses casos o erro aparece em `data/collector-health.json` e as outras fontes continuam rodando.
