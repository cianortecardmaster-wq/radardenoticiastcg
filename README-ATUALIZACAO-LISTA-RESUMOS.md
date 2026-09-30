# Atualização — lista + resumos

Arquivos alterados:

- `docs/index.html`
- `docs/app.js`
- `docs/style.css`
- `scripts/collect.py`
- `scripts/collect_official.py`

## O que muda na interface

- notícias passam a aparecer em uma lista compacta, uma por linha;
- título abre diretamente a matéria original;
- cada linha mostra jogo, idioma, oficial/não oficial, data, fonte e resumo;
- botões de curadoria continuam disponíveis;
- são mostradas 50 notícias por vez para a página não ficar pesada;
- botão `Mostrar mais notícias` carrega os próximos resultados;
- a busca também procura dentro dos resumos.

## O que muda no coletor

- tenta extrair resumo da própria listagem oficial;
- quando não encontra, busca `meta description` ou os primeiros parágrafos da matéria;
- limita essas visitas extras por fonte para evitar centenas de acessos a cada rodada;
- reaproveita resumos já gravados no `news.json` como cache;
- corrige a leitura de datas como `14 August 2026`;
- ignora datas muito futuras encontradas dentro do conteúdo;
- tenta descartar links de paginação;
- reconstrói os itens de coleta oficial em cada execução para limpar resultados antigos mal interpretados.

## Depois de enviar ao GitHub

Rode manualmente:

`Actions > Atualizar radar TCG > Run workflow`

Isso é importante porque os resumos das fontes oficiais serão preenchidos pelo novo coletor somente na próxima execução.
