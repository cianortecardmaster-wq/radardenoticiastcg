# Radar de curadoria social — FaB + Magic

Esta versão amplia o Radar TCG para descobrir conteúdo que pode servir de pauta, inspiração ou repostagem, além de notícias tradicionais.

## Novos tipos de conteúdo

- Arte / fanart / alters
- Memes / humor
- Jogadas / gameplay
- Discussões / opinião
- Vídeos / clips
- Comunidade
- Curiosidades

Os filtros antigos de notícias, lore, decks, combos, meta, regras, rumores, design e mercado continuam disponíveis.

## Reddit

O coletor consulta publicações novas e as mais votadas da semana. Para Flesh and Blood, acompanha r/FleshandBloodTCG. Para Magic, acompanha r/magicTCG, r/mtg, r/EDH, r/MTGmemes, r/magicthecirclejerking, r/edhcirclejerk, r/mtgaltered e r/custommagic.

Quando a API JSON pública do Reddit não responde, o coletor tenta o RSS como fallback. Posts marcados como +18 são ignorados.

Quando disponível, o Radar guarda pontuação, número de comentários e miniatura. A ordenação **Em circulação** usa esses sinais para colocar discussões e posts com mais interação no topo.

## Canais e podcasts

O diretório agora inclui Flesh and Blood e Magic, com filtro por jogo, plataforma e idioma. A configuração fica em `config/media_sources.yml`.

## Atualização

A janela continua limitada aos últimos 7 dias. O workflow existente continua rodando a cada 3 horas. Depois de subir estes arquivos, execute o workflow manualmente uma vez em **Actions > Atualizar radar TCG > Run workflow** para preencher as novas fontes sem esperar o próximo horário programado.
