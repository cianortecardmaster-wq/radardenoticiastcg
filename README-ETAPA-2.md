# Etapa 2 — fontes oficiais diretas

Copie este pacote sobre a raiz do repositório `radardenoticiastcg`, preservando as pastas.

Novos arquivos:
- `config/official_sources.yml`
- `scripts/collect_official.py`
- `data/collector-health.json`
- `docs/data/collector-health.json`

Substitua:
- `scripts/collect.py`
- `requirements.txt`

Depois execute:
`Actions > Atualizar radar TCG > Run workflow`

Confira em seguida:
- `data/news.json`
- `data/collector-health.json`

O radar passa a tentar fontes oficiais diretamente e continua usando Google News RSS como descoberta/fallback. Se um site bloquear robôs ou mudar o HTML, a falha fica registrada em `collector-health.json` sem derrubar o restante da coleta.
