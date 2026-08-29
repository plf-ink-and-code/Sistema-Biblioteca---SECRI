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
