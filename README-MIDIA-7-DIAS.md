# Canais & podcasts — conteúdo atual (7 dias)

A aba **Canais & podcasts** agora é alimentada pelo mesmo workflow que atualiza o radar a cada 3 horas.

## O que é coletado

- **YouTube:** o coletor resolve o canal, usa o feed oficial do canal quando possível e lista vídeos publicados nos últimos 7 dias.
- **Podcasts:** usa RSS/Atom; links do Apple Podcasts são resolvidos via iTunes Lookup e páginas Podbean têm descoberta automática do feed. Podcasts cadastrados via YouTube usam a busca recente do próprio YouTube.
- **Twitch:** coleta VODs recentes em modo *best effort* a partir da página pública do canal. Itens sem data verificável não entram, para nunca furar a janela de 7 dias.

Cada fonte mantém no máximo 12 conteúdos recentes. Conteúdo com mais de 7 dias é eliminado tanto no coletor quanto na interface.

## Primeira atualização

Os arquivos `data/media.json` e `docs/data/media.json` enviados no patch começam como catálogo, com `content_ready: false`. Depois de subir os arquivos, execute uma vez:

**Actions → Atualizar radar TCG → Run workflow**

Depois disso, o workflow grava automaticamente os links recentes e continua renovando a aba a cada 3 horas.

## Interface

Por padrão a aba mostra **somente canais que publicaram nos últimos 7 dias**. O filtro "Todos os canais" continua disponível para consultar o diretório inteiro, mas não exibe conteúdo vencido.
