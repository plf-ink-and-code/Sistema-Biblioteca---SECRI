# AGENT.md — Sistema Biblioteca SECRI

Guia para agentes de IA (e humanos) trabalhando neste repositório. Leia antes de
alterar qualquer coisa.

> Histórico detalhado de decisões e pegadinhas: ver `LEARNINGS.md`.

---

## O que é

Sistema de gestão de biblioteca escolar (SECRI). App desktop/web com NiceGUI,
SQLite, empréstimos, notificação de atrasos por e-mail, backup e audit log.

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Linguagem | Python 3.11 |
| UI | NiceGUI 2.15.0 |
| Banco | SQLite (modo WAL) em `data/biblioteca.db` |
| PDF | ReportLab (geração), pdfplumber (extração de acervo) |
| E-mail | smtplib (SMTP via env) |
| Deploy | Docker / `docker compose up -d --build` (máquina local, sem CI) |

## CRITICAL: builds e execução via Docker

A máquina NÃO tem Python/SDKs instalados. Tudo roda em container:

```bash
# Testes
docker run --rm -v "$(pwd):/src" -w /src python:3.11-slim \
  sh -c "pip install -r requirements.txt -q && pytest tests/ -v"

# Subir o app
docker compose up -d --build
```

**PEGADINHA (ver LEARNINGS)**: editar código NÃO atualiza a imagem buildada.
Sempre `docker compose up -d --build` após mudar código, senão o compose reusa a
imagem antiga.

## Estrutura

```
Sistema-Biblioteca---SECRI/
├── seed.py                 # Popula o banco — LÊ de livros.json (não mais array)
├── livros.json             # Acervo: [{title, author, category, year, copies}] (fonte do seed)
├── livros_unificado.csv    # Mesmo acervo em CSV (nome, autor, ano, categoria)
├── Planilha de Livros - V14.xlsx  # Fonte A (13 abas), revisada à mão
├── copias_fonte.txt        # Fonte D (manual): livros com N exemplares
├── tools/
│   ├── extract_books_xlsx.py  # ATUAL: xlsx V14 (A) + SECRICl/Página1 (B,C) + copies (D)
│   ├── parse_copias.py     # Parser da fonte D (copias_fonte.txt)
│   ├── extract_books.py    # LEGADO: 3 PDFs (fornece parse_pdf2/parse_pdf3 reusados)
│   ├── enrich_web.py       # Completa 'ano' faltante via Open Library/Google Books
│   └── enrich_cache.json   # Cache das buscas web
├── src/
│   ├── database.py         # Schema + conexão SQLite (DB_PATH via env)
│   ├── auth.py             # Login admin (PBKDF2, rate limit, sessão)
│   ├── backup.py / backup_remote.py
│   ├── notifier.py         # E-mail de atrasos (SMTP)
│   ├── main.py             # Bootstrap NiceGUI + timers de servidor
│   ├── services/           # books, loans, students, stats, audit, utils
│   └── gui/                # theme, login, library, students, dialogs, pdf, app
├── tests/                  # pytest (ver README; cobertura ~98%) + e2e_playwright.py
├── data/                   # biblioteca.db + backups/ (no .gitignore)
└── LEARNINGS.md            # Decisões/correções por sessão
```

## Acervo de livros (importação)

O `seed.py` popula a tabela `books` a partir de **`livros.json`** (1584 livros),
montado de **três fontes**. Não editar `livros.json` à mão sem necessidade;
preferir regenerar pelos scripts.

| # | Fonte | Arquivo | Natureza |
|---|-------|---------|----------|
| A | Planilha V14 | `Planilha de Livros - V14.xlsx` (13 abas `PDF_1..PDF_13`) | Revisada à mão; ano/categoria já preenchidos. Substitui o antigo PDF1 "Planilha V10". |
| B | SECRICl | `Livros SECRICl.pdf` | Texto corrido (`parse_pdf2`). |
| C | Página1 | `Livros SECRI - Página1.pdf` | Tabular embaralhado (`parse_pdf3`). |

`extract_books_xlsx.py` lê a planilha V14 (A) e **reusa** `parse_pdf2`/`parse_pdf3`
do `extract_books.py` para B e C. Duplicatas são **mantidas** (cada linha pode ser
um exemplar físico) — sem dedup.

### Regenerar o acervo

```bash
# 1) monta o JSON/CSV das 3 fontes (A=xlsx V14, B e C=PDFs). REGRAVA ambos.
docker run --rm -v "$(pwd):/src" -w /src python:3.11-slim \
  sh -c "pip install -q pdfplumber openpyxl; \
         PYTHONPATH=/src/tools python3 tools/extract_books_xlsx.py"

# 2) completa 'ano' faltante via web (usa cache, não re-busca)
docker run --rm -v "$(pwd):/src" -w /src python:3.11-slim \
  sh -c "pip install -q requests; python3 tools/enrich_web.py"
```

**Ordem importa**: o extractor regrava o JSON/CSV; rodar o enrich depois. O cache
(`tools/enrich_cache.json`) evita refazer as buscas.

**Enriquecimento só afeta B e C**: a planilha V14 (A) já vem com todos os anos, logo
nenhuma linha de A entra na lista de "sem ano" do `enrich_web.py` — ele só toca B e C.

### Como os parsers funcionam (resumo)

- **xlsx V14** (A): 13 abas, cabeçalho `Nome|Autor|Ano|Categoria|Página(s)|Confiança`.
  Lido com openpyxl (`data_only=True`). `Página(s)` e `Confiança` são descartadas.
  Ano `1987.0`→`1987`; autor `"Não identificado…"`/vazio → `null`.
- **PDF3** (C) tabular: text-layer EMBARALHADO. Lido em ORDEM DE STREAM (chars na
  ordem bruta) — aí cada célula fica contígua. Título = 1ª run; separação
  título/autor pela coluna-autor (x fixo) + heurística de salto/maiúscula.
- **PDF2** (B) texto corrido: `Nome, Autor, Categoria, Ano`; registros fecham ao
  terminar em ano ou quando a próxima linha inicia novo título.
- Detalhes e pegadinhas em `LEARNINGS.md` e nas docstrings dos scripts.

### Fonte D — cópias (exemplares) escrita à mão

`copias_fonte.txt` (raiz) registra livros com **múltiplos exemplares**, no formato
de 4 linhas por registro, separados por vírgula:

```
Título
Autor
Ano
Categoria N cópias,      ← categoria + quantidade; vírgula = fim do registro
```

`tools/parse_copias.py` extrai `{title, author, year, category, copies}` (aceita
`cópias`/`copias`, sing/plural). O `extract_books_xlsx.py` aplica essa contagem
por match **título+autor** (fallback só-título) no acervo; livros sem registro
ficam `copies = 1`. Não há dedup — duplicatas continuam como linhas separadas.

### Campos obrigatórios vs opcionais

- `title`: obrigatório. `author`: `NOT NULL` no schema → nulo vira
  `"Autor desconhecido"` no seed. `category` e `year`: OPCIONAIS (ficam `NULL`).
- `copies`: total de exemplares, `NOT NULL DEFAULT 1`.
- NÃO inventar ano/categoria quando não há fonte confiável.

## Banco de dados

- `books(id, code, title, author NOT NULL, category, year, copies NOT NULL DEFAULT 1, available)`.
- **Modelo de exemplares**: disponibilidade = `copies − empréstimos ativos`
  (não é mais o booleano `available`, que é só reconciliado p/ compatibilidade).
  - `loan_book` bloqueia quando `ativos >= copies` ("Não há exemplares disponíveis").
  - `return_book` fecha o empréstimo ativo **mais antigo** daquele livro.
  - `services.available_count(book_id)` → exemplares livres.
  - `books_with_status(...)` agrega ativos por livro e expõe
    `copies`, `available_count`, `copies_label` ("disp./total"), e `status`
    (`Disponível` / `Esgotado` / `Atrasado`).
- **Filtro alfabético**: `services.list_by_initial(letra)` e o param `initial` de
  `books_with_status` (`"0-9"` = começa com dígito via GLOB; letra via `LIKE 'X%'`).
  Na UI: barra A–Z (Todos / 0-9 / A..Z).
- Migração idempotente: `database.init_db` faz `ALTER TABLE books ADD COLUMN copies`
  em bancos antigos (silencioso se já existe).
- `DB_PATH` via env (default `data/biblioteca.db`). Para testar o seed sem tocar
  o banco real: `DB_PATH=/tmp/test.db`.
- Rodar o seed como o projeto faz:
  `docker exec -e PYTHONPATH=/app/src <container> python /app/seed.py`.

## UI (tema dark/light)

- `src/gui/theme.py` é a **fonte única** de cores/tokens/componentes. Telas chamam
  `theme.apply()` no topo; nada de cor hardcoded.
- Tema **dark** (Catppuccin) e **light** (teal SaaS) com toggle persistido em
  `app.storage.user["theme"]` (`theme.theme_toggle()`).
- Regras obrigatórias de NiceGUI em `.kiro/steering/ui-nicegui.md` (sem `gap-*`,
  rodapé de diálogo sticky, validação Playwright). **Ler antes de mexer na UI.**
- Validar UI com Playwright via Docker — ver `tests/e2e_playwright.py` e o steering.

## Convenções

- Caminhos relativos / env vars; nada hardcoded de `$HOME`.
- Mudou código → `docker compose up -d --build`.
- Toda feature/bugfix acompanha teste (pytest). Rodar antes de propor commit.
- UI: seguir `.kiro/steering/ui-nicegui.md` (gap, tema, rodapé, Playwright).
- Segredos (`.env`: SMTP_PASSWORD etc.) NUNCA commitar nem ecoar em logs.
- Documentar: ao mexer em algo relevante, atualizar `LEARNINGS.md` e, se afetar
  estrutura/fluxo, este `AGENT.md`.

## Git

- NÃO commitar/pushar sem pedido explícito do usuário.
- Commits no formato Conventional Commits.
- `data/`, backups e segredos fora do versionamento.

## Pendências conhecidas

- ~6 linhas do PDF2 com vírgula dentro do título precisam de ajuste manual p/ 100%.
- Possíveis títulos duplicados no acervo (pode ser exemplar real) — confirmar
  antes de dedupe.
- Tela de visualização do audit log ainda não existe (só `list_audit()`).
- Backup remoto para Google Drive: ver TODO no `LEARNINGS.md`.
