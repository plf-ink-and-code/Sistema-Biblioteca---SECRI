# Learnings — Sistema Biblioteca SECRI

Registro de decisões, correções e contexto para retomar em sessões futuras.

---

## [2026-08-28] Sessão: Connection lost + performance + login + melhorias + backup/audit

**Stack**: Python 3.11, NiceGUI 2.15.0, SQLite (WAL), ReportLab, Docker (compose).
Deploy: máquina local, `docker compose up -d --build`. Sem CI (removido a pedido).

### Correção do "Connection lost" (causa raiz)

- **Causa principal**: I/O bloqueante no event loop asyncio do NiceGUI trava o
  WebSocket → browser mostra "Connection lost" e reconecta quando o loop
  desbloqueia.
  - SMTP síncrono (`smtplib`) rodava no event loop (timer + botão Notificar
    Gestor). Sem timeout, podia travar dezenas de segundos.
  - `_refresh` da tabela tinha N+1 de queries (active_loan + is_overdue por linha).
- **Correções**:
  - SMTP movido para thread via `nicegui.run.io_bound`; callbacks viraram `async`.
  - Timeout no `smtplib.SMTP(..., timeout=SMTP_TIMEOUT)` (default 10s).
  - `services.books_with_status()` — 1 JOIN (books LEFT JOIN empréstimo ativo),
    filtro de categoria no SQL, sem `dict()` intermediário.
  - SQLite WAL + `synchronous=NORMAL`; índices em loans(book_id,return_date) e
    loans(return_date,deadline_date).
  - Healthcheck leve `/health` (endpoint dedicado, não serve a SPA inteira).

- **PEGADINHA IMPORTANTE**: o container rodava a IMAGEM ANTIGA. Editar código não
  altera a imagem buildada. **Sempre `docker compose up -d --build`** após mudar
  código, senão o compose reusa a imagem velha. Foi por isso que "seguia dando o
  erro" mesmo com o código corrigido. Diagnóstico: `/health` dava 404 e `GET /`
  levava 41s na imagem velha.

### Performance (benchmark medido, 5000 livros)

- `books_with_status` filtro categoria: 18.6ms → 3.4ms (−82%, filtro no SQL).
- `books_with_status` todos: 20.2ms → 12.2ms (−40%, sem dict() + WAL).
- Script: `tests/benchmark.py` (rodar via Docker, ver README).

### Autenticação (admin único)

- `src/auth.py`: `verify_credentials` time-safe (`hmac.compare_digest`).
  Senha via **PBKDF2-HMAC-SHA256** (120k iter, salt derivado de AUTH_SECRET).
- Rate limiting em memória (LOGIN_MAX_ATTEMPTS=5, LOGIN_COOLDOWN_SECS=300).
  ⚠️ É por processo, não compartilhado entre réplicas (ok para single-container).
- Expiração de sessão: `is_session_valid` (SESSION_MAX_AGE_HOURS=8).
- `app.storage.user` + `storage_secret` no `ui.run`. AuthMiddleware
  (BaseHTTPMiddleware) redireciona não-autenticados p/ /login; libera /login,
  /health, /_nicegui*.
- `gui/login.py` página /login; botão logout no header da library.
- Config via env: ADMIN_USER (admin), ADMIN_PASSWORD (admin123 — DEV ONLY),
  AUTH_SECRET.

### Outras melhorias

- **Timer global**: notificação de atrasos virou `app.timer` + `@app.on_startup`
  (era `ui.timer` preso ao cliente — bug: não rodava sem aba aberta). Roda em
  run.io_bound. OVERDUE_CHECK_INTERVAL (default 3600).
- Feedback loading no botão Notificar Gestor.
- Layout do login responsivo (min-height 100vh, não absolute-center).
- `students.py`: form add/edit unificado em `_student_dialog`.
- Coluna órfã `deadline_days` removida (schema + migration DROP COLUMN
  idempotente; SQLite 3.46 suporta).

### Backup + Audit (implementado hoje)

- `src/backup.py`: `create_backup` usa `sqlite3.backup()` (consistente com WAL,
  NÃO usar `cp`). `rotate` mantém BACKUP_KEEP (7). `run_backup` = create+rotate.
  Job `app.timer(BACKUP_INTERVAL default 86400)` em main.py, run.io_bound.
  Backups em `data/backups/` (no volume + .gitignore). NOTA: app.timer dispara
  1x no startup — backup roda ao subir o container.
- Audit: tabela `audit_log(id,ts,username,action,detail)`; `services/audit.py`
  `log_action` + `list_audit`. Gravado na UI (library `_on_done`, students
  `_audit`) usando `app.storage.user['username']`.
  ⚠️ Grava mas NÃO tem tela de visualização ainda (só `list_audit()`).

### Documentação

- README com seção **Arquitetura** (4 diagramas Mermaid: deploy, camadas,
  fluxo de auth [sequence], jobs de servidor). Padrão devops-docs.
- `.env.example` completo. 101 testes, cobertura 98% (auth/audit 100%,
  backup 95%, database 94%).

---

## TODO / próxima sessão

1. **Enviar backup para Google Drive do gestor** (PEDIDO, adiado):
   - Recomendado: **Service Account** (não expira, sem login interativo).
     Gestor compartilha pasta do Drive com o e-mail da SA; storage conta na
     conta dele.
   - Alternativas: OAuth refresh token; ou `rclone copy` (mais simples op.,
     add binário na imagem).
   - Usuário vai gerar a credencial (JSON) no Google Cloud — agent implementa o
     consumo via env/arquivo montado (secret, nunca commitar). Testar com client
     Google mockado; upload real fica com o usuário.
   - Definir: todo backup ou 1/dia? manter local também (sim)? retry no fail?
   - Precisa: ID da pasta do Drive compartilhada.

2. **Tela de visualização do audit log** (/auditoria protegida) — opcional.

3. **Múltiplos exemplares por livro** — invasivo (muda modelo `available`
   booleano + UI de empréstimo). Confirmar comportamento antes.

4. **Commit**: NADA foi commitado ainda nesta sessão. Todas as mudanças estão
   apenas no working tree. Preparar commit(s) quando o usuário pedir.

5. Considerar: rate limiter compartilhado (Redis) se um dia escalar horizontal;
   testes E2E no browser (Playwright) para validar fluxo de login completo.


---

## [2026-11-08] Sessão: Importar livros de 3 PDFs → livros.json + seed.py lê do JSON

**Objetivo**: transformar PDFs de acervo em planilha unificada e depois em JSON
que o `seed.py` consome (substituindo o array `BOOKS` hardcoded de 180 clássicos).

### Fontes (3 PDFs na raiz do repo)

| PDF | Formato | Parser |
|-----|---------|--------|
| `Planilha de Livros - V10 - Planilha de Livros - V10.pdf` | Tabular, text-layer EMBARALHADO | `parse_pdf1` |
| `Livros SECRICl.pdf` | Texto corrido `Nome, Autor, Categoria, Ano` | `parse_pdf2` |
| `Livros SECRI - Página1.pdf` | Tabular, text-layer EMBARALHADO | `parse_pdf3` |

### DESCOBERTA CRÍTICA: text-layer embaralhado (PDF1 e PDF3)

Os PDFs tabulares têm o text-layer com DOIS text-runs interleaved em x (pdfplumber
`extract_text`/`extract_tables` retorna lixo tipo `Ave Jorge (Arte p` +
`aZriraa Cldroia...`). **MAS em ORDEM DE STREAM (ordem bruta dos chars, sem
ordenar por posição) cada célula fica contígua e limpa.**

Solução (`tools/extract_books.py`, função `_title_and_tail`):
1. Ler `page.chars` agrupados por `round(top)` (linha), em ordem de stream.
2. Título = 1ª "run" de chars (x crescente). Separa do autor quando o char cai
   na banda x EXATA da coluna autor E (salto grande >8.5px OU é MAIÚSCULA OU x
   recuou = backward jump). Títulos que transbordam fluem com gaps pequenos e
   minúsculas → não disparam a separação.
3. Cauda (autor+ano+categoria+...) parseada da DIREITA p/ ESQUERDA:
   confiança (alta/média/baixa) → página (dígitos) → categoria (lista conhecida)
   → ano (`-?\d{3,4}`, suporta a.C. ex. -750) → autor (resto).

Coordenadas das colunas (medidas no text-layer):
- PDF1: autor x≈272.1 | categoria x≈423.6 | página x≈541 | confiança x≈572
- PDF3: autor x≈310.0 | categoria x≈385 | ano x≈460

**PEGADINHA PDF3**: categoria/ano quase sempre VAZIOS na fonte; o autor transborda
para a zona-x da categoria. Só aceitar categoria se casar na lista `CATEGORIES`
conhecida (senão é lixo do autor).

**Outras pegadinhas**:
- Títulos que quebram em 2 linhas visuais: linha SEM confiança no fim (PDF1) ou
  sem autor/ano/categoria (PDF3) = continuação → concatenar no título anterior.
- PDF2: vírgula DENTRO do título (ex. "Turma da Mônica (Bom dia, Boa tarde)",
  "1808 (...)") confunde o split por vírgula. ~6 linhas afetadas, aceitável.
- OCR (tesseract) NÃO resolve: a renderização visual TRUNCA a célula pela largura
  da coluna. A leitura por stream-order é superior.

### Enriquecimento web (`tools/enrich_web.py`)

- Para livros SEM ano (com autor), busca ano na **Open Library** (pública, sem
  chave) com fallback **Google Books**. Só preenche se título+autor baterem
  (token_overlap ≥ 0.5). Cache em `tools/enrich_cache.json` (não re-busca).
- Google Books deu HTTP 429 (quota do IP compartilhado estourada) → Open Library
  é a fonte confiável. Resultado: **+57 anos** recuperados e validados.
- Decisão: NÃO inventar ano p/ obras sem metadado público (mangás, edições
  específicas, obras locais). Ficam `null` — year/category são OPCIONAIS.

### Resultado

- **1146 livros** no total: PDF1=767, PDF2=141, PDF3=238.
- Cobertura: autor 1108/1146, ano 926/1146, categoria 880/1146.
- Artefatos: `livros_unificado.csv` (nome, autor, ano, categoria) e `livros.json`
  (`{title, author, category, year}`, year int ou null).

### seed.py agora lê livros.json

- Removido o array `BOOKS` hardcoded (180 clássicos).
- `load_books()` lê `livros.json` → tuplas `(title, author, category, year)`.
  Path via env `BOOKS_JSON` (default: `livros.json` ao lado do seed).
- **IMPORTANTE (schema)**: `books.author` é `NOT NULL`. author nulo no JSON vira
  `"Autor desconhecido"`. category/year nulos ficam `NULL`.
- Testado em banco temporário (`DB_PATH=/tmp/...`, NÃO tocou `data/biblioteca.db`):
  `Done: 1146 books (30 loaned)`, year NULL 220, category NULL 266, author NULL 0.
- Rodar como o projeto faz: `docker exec -e PYTHONPATH=/app/src <cid> python /app/seed.py`.

### Fluxo para regenerar

```bash
# 1) extrai os 3 PDFs -> CSV + JSON (regrava, apaga enriquecimento)
docker run --rm -v "$(pwd):/src" -w /src python:3.11-slim \
  sh -c "pip install -q pdfplumber; python3 tools/extract_books.py"
# 2) complementa anos faltantes via web (usa cache)
docker run --rm -v "$(pwd):/src" -w /src python:3.11-slim \
  sh -c "pip install -q requests; python3 tools/enrich_web.py"
```
Ordem importa: o extractor regrava CSV/JSON; o cache do enrich evita re-buscar.

### Decisão do usuário

- Removida a coluna `fonte` do CSV (rastreava origem PDF1/2/3) — não foi pedida.

### Arquivos criados/alterados nesta sessão

- `tools/extract_books.py` (novo) — parser dos 3 PDFs.
- `tools/enrich_web.py` (novo) — enriquecimento de ano via Open Library/Google Books.
- `tools/enrich_cache.json` (novo) — cache das buscas web.
- `livros_unificado.csv`, `livros.json` (gerados).
- `seed.py` (alterado) — lê livros.json em vez do array BOOKS.
- `AGENT.md`, `CLAUDE.md` (novos) — guia para agentes.

### TODO / próxima sessão

1. ~6 linhas do PDF2 com vírgula no título precisam de ajuste manual se quiser 100%.
2. Linha "A Idade de Cada Um" (PDF3): separação título/autor caiu no meio — isolada.
3. NADA commitado ainda — mudanças só no working tree.
4. Considerar dedupe: há títulos repetidos (ex. "Teia Tecendo Aranha") — pode ser
   exemplar real duplicado na fonte; confirmar antes de remover.

---

## [2026-11-15] Sessão: Planilha V14 (xlsx) + 2 PDFs → livros.json unificado

**Objetivo**: substituir a antiga Planilha V10 (PDF1) pela **Planilha de Livros -
V14.xlsx** (revisada à mão, 13 abas) e **juntar** com os dois PDFs que NÃO são
planilha (`Livros SECRICl.pdf` = B, `Livros SECRI - Página1.pdf` = C),
complementando ANO faltante de B e C pela web.

### Fontes

| # | Arquivo | Natureza | Parser |
|---|---------|----------|--------|
| A | `Planilha de Livros - V14.xlsx` (13 abas `PDF_1..PDF_13`) | Revisada; ano/categoria preenchidos | openpyxl (novo) |
| B | `Livros SECRICl.pdf` | Texto corrido | `parse_pdf2` (reusado) |
| C | `Livros SECRI - Página1.pdf` | Tabular embaralhado | `parse_pdf3` (reusado) |

### Decisões do usuário

1. **Manter duplicatas** (sem dedup) — cada linha pode ser exemplar físico; dedup
   será tratado depois.
2. **Web só para B e C** — a planilha V14 (A) já vem com todos os anos.

### Novo script: `tools/extract_books_xlsx.py`

- Lê as 13 abas do xlsx com `openpyxl` (`data_only=True`); pula cabeçalho e linhas
  vazias. Descarta colunas `Página(s) no PDF` e `Confiança` (não há no schema).
- **Reusa** `parse_pdf2`/`parse_pdf3` + constantes `PDF2`/`PDF3` importando de
  `extract_books` (precisa `PYTHONPATH=/src/tools` ao rodar da raiz).
- Normalização: ano `1987.0`→`1987` (regex `^(-?\d{3,4})(?:\.0+)?$`, mantém a.C.
  negativo); autor `"Não identificado…"`/`-`/vazio → `null`; categoria vazia → `null`.
- Saída: `livros.json` (A+B+C na ordem) + `livros_unificado.csv`.

### Enriquecimento naturalmente escopado a B e C

O `enrich_web.py` não foi alterado: ele busca só linhas **sem ano com autor**.
Como A (xlsx) tem 0 sem ano, só B e C entram. Resultado desta rodada:

- Candidatos sem ano (com autor): 270 → **57 preenchidos do cache** (0 buscas live;
  cache de 258 da sessão anterior cobriu tudo; 0 uncached, nada pulado).
- 213 restantes ficaram `null` (cacheados como "sem metadado público" — títulos
  locais/edições específicas). **Regra do projeto: não inventar ano.**

### Resultado final (`livros.json`)

- **1584 livros** (A=1205, B=141, C=238), duplicatas mantidas.
- Com ano: 1365 | sem ano: 219 (todos de B/C) | sem autor: 182 | sem categoria: 265.
- Ano min/max: **-750** (Ilíada) a **2022**.
- A (primeiros 1205 no JSON) permanece intacta: 0 sem ano após o enrich.

### Fluxo para regenerar

```bash
docker run --rm -v "$(pwd):/src" -w /src python:3.11-slim \
  sh -c "pip install -q pdfplumber openpyxl; \
         PYTHONPATH=/src/tools python3 tools/extract_books_xlsx.py"
docker run --rm -v "$(pwd):/src" -w /src python:3.11-slim \
  sh -c "pip install -q requests; python3 tools/enrich_web.py"
```

### Pegadinhas / notas

- O xlsx tem valores numéricos como float (`1987.0`, `1.0`) por vir de célula
  numérica — daí o regex que tolera `.0`.
- `extract_books.py` (legado, 3 PDFs) NÃO foi removido: ainda fornece os parsers
  `parse_pdf2`/`parse_pdf3`. A antiga `Planilha V10.pdf` deixou de ser fonte.
- NADA commitado — mudanças só no working tree.

### TODO / próxima sessão

1. Dedup (combinado com o usuário: tratar "em breve"). Há duplicatas intra-fonte
   e possivelmente entre A e B/C.
2. 219 livros ainda sem ano (B/C sem metadado público) — aceitável por regra.

---

## [2026-11-15] Sessão (cont.): Múltiplos exemplares (copies) + filtro alfabético A-Z

**Objetivo**: suportar livros com **vários exemplares** (ex. "50 cópias") — na hora
de emprestar mostrar quantos há disponíveis e bloquear quando esgotar — e adicionar
na UI uma **seleção por letra do alfabeto** (inicial do título).

### Fonte D (nova, escrita à mão): `copias_fonte.txt`

Formato = 4 linhas por registro, separados por vírgula:
`Título / Autor / Ano / "Categoria N cópias,"`. O "N cópias" **NÃO** está nos PDFs
originais (grep no PDF2 = 0 ocorrências) — é uma fonte que o usuário digitou.

`tools/parse_copias.py` extrai `{title, author, year, category, copies}`
(regex `(\d+)\s*c[oó]pias?`). `extract_books_xlsx.py` aplica por match
**título+autor** normalizado (fallback só-título), default `copies=1`.
Confirmados nesta sessão: O menino das pernas compridas=50, Cientistas Mirins=17,
E se o mundo descostura?=29. Total: 1584 livros / **1677 exemplares físicos**.

### Mudança de MODELO (invasiva): booleano → contagem

Antes: `books.available` 0/1 (1 livro = 1 exemplar). Agora:
`books.copies NOT NULL DEFAULT 1`; disponibilidade = `copies − empréstimos ativos`.

- `loans.loan_book`: valida `ativos < copies`, senão `ValueError("Não há exemplares
  disponíveis...")` (antes era "já está alugado").
- `loans.return_book`: fecha o empréstimo ativo **mais antigo** (ORDER BY loan_date, id).
- `loans.available_count(book_id)` novo; `_sync_available` reconcilia o booleano
  legado (mantido por compatibilidade, não é mais a fonte da verdade).
- `books_with_status`: **agrega** ativos por livro (COUNT, pois agora há N ativos),
  expõe `copies`/`available_count`/`copies_label` ("disp./total"); status
  `Disponível`/`Esgotado`/`Atrasado`. **"Alugado" virou "Esgotado"** → ajustei
  3 testes antigos + badge/filtro na GUI.
- `stats.dashboard_stats`: exemplar-aware (exemplars = SUM(copies), loaned = ativos).

### Filtro alfabético A-Z

- `books.list_by_initial(letra)` + param `initial` em `books_with_status`.
  `"0-9"` → `substr(title,1,1) GLOB '[0-9]'`; letra → `title LIKE 'X%'`
  (LIKE do SQLite é case-insensitive p/ ASCII). Índice `idx_books_title` já existia.
- GUI `library.py`: barra de botões Todos / 0-9 / A..Z, com highlight do ativo;
  combina com filtros de categoria/status.

### seed.py

Insere `copies`; gera 30 empréstimos ativos **respeitando** o total por livro
(loop que só empresta se `ativos < copies`). Validado em DB temp: 0 livros com
ativos > copies.

### Pegadinha de ambiente

- `data/` é **root-owned** (criado pelos `docker run`), então não dá pra escrever
  `data/copias.txt` como usuário → fonte foi pra raiz (`copias_fonte.txt`).
- `ui.number` do NiceGUI para o campo Cópias (min=1).

### Validação

- Via Docker: **135 testes passam**, cobertura services **98%** (books 100%,
  loans 98%, stats 100%). Novo arquivo `tests/test_copies.py` (copies loan/return/
  esgotado/atrasado + filtro A-Z + edição de copies).
- `DB_PATH=/tmp/seedtest.db python seed.py` → "1584 books (1677 exemplars, 30 active)".

### TODO / próxima sessão

1. Dedup (ainda pendente). Com `copies`, parte das duplicatas intra-fonte pode
   virar contagem em vez de linhas repetidas — decidir critério com o usuário.
2. Popular o banco REAL (`data/biblioteca.db`) é destrutivo (seed faz DELETE +
   empréstimos fake) — fazer backup antes e confirmar com o usuário.
3. NADA commitado — mudanças só no working tree.

---

## [2026-11-15] Sessão (cont. 2): Redesign da UI (tema dark/light) + Playwright

**Objetivo**: deixar a UI "mais bonita". Pesquisei skills/design systems de frontend
na web e apliquei: tema centralizado dark **e** light com toggle, componentes
reutilizáveis, e validação com teste de browser real (Playwright).

### Pesquisa (fontes úteis)

- Skill "pythonista-nicegui" (LobeHub) → **regras técnicas** que viram gotchas:
  nunca usar `gap-*` do Tailwind (bug #2171 no Ubuntu; usar `style("gap: Xrem")`);
  botões de diálogo **sticky** no rodapé; `min-width:0` em flex lado a lado;
  não usar `height:100%` dentro de `max-height`.
- Design system SaaS (gist rvanbaalen) → paleta **light** teal (#18b69b),
  tokens de raio/sombra/tipografia (Inter), badges sutis.

### `src/gui/theme.py` (novo) — fonte única

- Paletas DARK (Catppuccin) e LIGHT (teal SaaS); `apply()` seta `ui.colors` +
  `ui.dark_mode` + CSS global (Inter, scrollbar, hover de linha, `.sb-card`).
- Tokens: RADIUS, SHADOW, FONT, GAP. Helpers: `stat_card` (clicável),
  `section_card`, `page_header`, `dialog_shell` (retorna dialog/body/**footer
  sticky**), `theme_toggle`.
- Toggle persiste em `app.storage.user["theme"]` e dá `ui.navigate.reload()`.
- `main.py`: removido `dark=True` do `ui.run` (agora o tema por página controla).

### Telas refeitas

`login` (card com identidade + toggle), `library` (header com usuário+toggle,
6 cards de dashboard **clicáveis** que filtram, barra de ações com ícones,
filtro A–Z como `ui.toggle` compacto, tabela com hover + badge outline + estado
vazio `no-data`), `students` e `dialogs` (todos com `dialog_shell`). **Zero
`gap-*`** e zero cor hardcoded restante no GUI.

### Validação Playwright via Docker

- App via `docker compose up -d --build` (rede `sistema-biblioteca---secri_default`).
- `tests/e2e_playwright.py` roda em `mcr.microsoft.com/playwright/python:v1.47.0-jammy`
  anexado à rede, `BASE_URL=http://biblioteca:8080`, login admin/admin123.
- **GOTCHA**: a imagem traz só os browsers (chromium-1134), NÃO o pacote Python.
  Instalar `playwright==1.47.0` (== tag da imagem). Se instalar "latest", o browser
  não bate → "Executable doesn't exist". 
- Checks (todos passaram): cards do dashboard, tabela, botões, filtro A, **toggle
  de tema**, página de alunos, diálogo Adicionar com campo Cópias. Screenshots em
  `e2e_out/` revisados: dark e light OK visualmente.
- 135 unit tests continuam passando (lógica intacta).

### Steering novo

Criado `.kiro/steering/ui-nicegui.md` com as regras (gap, tema, rodapé sticky,
Playwright, checklist). É o primeiro `.kiro/` do projeto.

### TODO / próxima sessão

1. Coluna "Status" aparece cortada no screenshot full-page (scroll horizontal da
   tabela) — cosmético; avaliar esconder "E-mail" em telas estreitas (responsivo).
2. Responsividade mobile da barra de ações/filtros.
3. NADA commitado — mudanças só no working tree.

---

## [2026-11-15] Sessão (cont. 3): Limpeza do acervo + ajustes de UI

**Pedidos do usuário**: (1) remover títulos ininteligíveis; (2) disponibilidade
ANTES do aluno na tabela (info mais importante, sem rolar); (3) área da tabela
maior (usar largura do monitor); (4) destacar o card de dashboard ativo; (5)
remover o rodapé "Pronto.".

### Limpeza do acervo (reproduzível no pipeline)

`tools/extract_books_xlsx.py` ganhou `_clean_titles(allb)`:
- **REMOVE** (4): títulos que começam com "..."/"…" ou "Título ilegível ...".
- **LIMPA** (12, mantém o livro): tira parênteses de nota de legibilidade
  ("(título parcialmente coberto)", "(Globo, nº ilegível)", "(parcialmente
  legível)") e "- lombada parcialmente legível". Ex.: "Chico Bento (Globo, nº
  ilegível)" → "Chico Bento"; "Dora, a aventureira (título parcialmente coberto)"
  → "Dora, a aventureira".
- Decisão do usuário: o **número da edição não importa**, então os gibis com
  "nº ilegível" ficam (só perde a anotação). Só sai o que é título ininteligível.
- Resultado: 1584 → **1580 títulos** (1673 exemplares). Banco repopulado (backup
  `data/backups/biblioteca-preclean-*.db` antes).

### UI (library.py)

- Container: removido `max-w-6xl` → `max-width: 1800px` (usa quase todo o monitor).
- Colunas reordenadas: Nº · Título · **Disponível** · Status · Autor · Categoria ·
  Aluno (disponibilidade logo após o título).
- Dashboard: refatorado em `_build_dashboard()` que re-renderiza destacando o card
  do filtro ativo (`theme.stat_card(..., active=True)` → borda+glow na cor). Chamado
  em `_apply_filters`.
- Removido o card rodapé "Pronto." (`label_event`); feedback agora é `ui.notify`
  (toast bottom-right) em `_set_event`.

### Validação

- Playwright via Docker: checks novos passam (rodapé removido, coluna "Disponível"
  no cabeçalho, card ativo clicável) + os anteriores. Screenshot `02b_card_ativo.png`
  confirma card "Disponíveis" destacado, tabela larga, coluna de disponibilidade
  no começo.

### Pegadinha recorrente

`livros.json`/`.csv` viram **root-owned** após `docker run` escrever neles. Antes
de editar pelo host: `docker run --rm -v "$(pwd):/src" -w /src python:3.11-slim
chown $(id -u):$(id -g) livros.json livros_unificado.csv`.

### TODO

1. NADA commitado — tudo working tree.
2. Responsividade mobile (barra de ações/filtros) ainda pendente.
