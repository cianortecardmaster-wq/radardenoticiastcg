# Correção de datas — v1.3

Problema corrigido: entradas sem data de publicação estavam recebendo `now_iso()`.
Na prática, qualquer página antiga sem uma data reconhecida podia aparecer como publicada hoje.

A correção faz quatro coisas:

1. nunca mais usa a data da coleta como data de publicação;
2. tenta recuperar a data real na própria matéria por meta tags, `<time>` e JSON-LD;
3. se a data não puder ser verificada, a entrada é descartada em vez de aparecer como "hoje";
4. remove itens antigos gerados pela lógica anterior e rejeita datas com mais de 2 dias no futuro.

## Aplicação

Substitua na raiz do repositório:

- `scripts/collect.py`
- `scripts/collect_official.py`

Depois faça commit e execute:

`Actions > Atualizar radar TCG > Run workflow`

Essa primeira execução após a correção também limpa do `news.json` os itens antigos cuja data foi gerada pela lógica defeituosa.
