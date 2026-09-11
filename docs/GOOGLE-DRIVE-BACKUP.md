# Backup off-site no Google Drive (Service Account)

Este guia mostra como enviar os backups do banco para uma pasta do Google Drive,
automaticamente, usando uma **Service Account** (conta de robô). Isso tira os
backups da máquina local — proteção contra perda de disco / falha da máquina.

- **Custo: R$ 0.** Service Account e Google Drive API são gratuitos. Os arquivos
  ocupam a cota do Drive do gestor (os 15 GB grátis já bastam — cada backup tem
  poucos KB).
- **Não precisa ativar billing** (cartão de crédito) para nada deste guia.

O app já cria o backup local; o envio ao Drive é **opt-in**: só liga quando as
variáveis `GDRIVE_CREDENTIALS_FILE` e `GDRIVE_FOLDER_ID` estão definidas.

---

## Como funciona (resumo)

Uma Service Account tem um e-mail próprio (ex.:
`biblioteca-backup@projeto.iam.gserviceaccount.com`) e se autentica por um
**arquivo JSON de credencial** — sem login interativo, ideal para servidor/WSL.

Ela **não tem cota de Drive própria**, então o gestor **compartilha uma pasta**
do Drive dele com o e-mail da SA. Os backups são gravados nessa pasta e contam na
cota do gestor.

```
job de backup → cria .db local → upload pra pasta do gestor no Drive
                                    → rotação remota (mantém GDRIVE_KEEP recentes)
```

---

## Passo a passo (uma vez)

### 1. Criar um projeto no Google Cloud

1. Acesse https://console.cloud.google.com/
2. No topo, **selecionar projeto → Novo projeto**. Nome livre (ex.:
   `biblioteca-secri`). Criar.

### 2. Ativar a Google Drive API

1. Menu → **APIs e serviços → Biblioteca**.
2. Busque **Google Drive API** → **Ativar**.

### 3. Criar a Service Account

1. Menu → **APIs e serviços → Credenciais**.
2. **Criar credenciais → Conta de serviço**.
3. Nome: `biblioteca-backup` (o e-mail é gerado automaticamente). **Concluir**
   (não precisa dar papéis/roles do projeto — a permissão vem do
   compartilhamento da pasta).

### 4. Gerar a chave JSON

1. Na lista de contas de serviço, clique na que você criou.
2. Aba **Chaves → Adicionar chave → Criar nova chave → JSON → Criar**.
3. O navegador baixa um arquivo `.json`. **Guarde com cuidado — é uma chave
   privada. Nunca faça commit dele.**

### 5. Compartilhar a pasta do Drive (feito pelo gestor)

1. No Google Drive do gestor, crie uma pasta (ex.: `Backups Biblioteca`).
2. Abra a pasta e copie o **ID** da URL:
   ```
   https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz
                                            └──────────── este é o FOLDER_ID
   ```
3. **Compartilhar** a pasta com o **e-mail da Service Account** (aquele
   `...@...iam.gserviceaccount.com`), com permissão de **Editor**.

---

## Configurar no servidor

1. Copie o JSON da Service Account para a máquina servidora, num caminho fora do
   git (ex.: `./secrets/gdrive.json` — a pasta `secrets/` deve estar no
   `.gitignore`; ou monte como Docker secret).

2. No `.env`, defina:
   ```bash
   GDRIVE_CREDENTIALS_FILE=/app/secrets/gdrive.json
   GDRIVE_FOLDER_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz
   GDRIVE_KEEP=30
   ```

3. Monte o JSON dentro do container. No `docker-compose.yml`, adicione um volume
   (read-only) apontando para o arquivo:
   ```yaml
   services:
     biblioteca:
       volumes:
         - ./data:/app/data
         - ./secrets/gdrive.json:/app/secrets/gdrive.json:ro
   ```

4. Recrie o container (com `--build`, pois o `requirements.txt` mudou):
   ```bash
   docker compose up -d --build
   ```

O backup roda uma vez no startup, então logo você deve ver o arquivo aparecer na
pasta do Drive. Nos logs do container (`docker compose logs -f biblioteca`)
aparece `backup enviado ao Drive (id=...)`.

---

## Variáveis

| Variável | Obrigatória | Default | Descrição |
|----------|-------------|---------|-----------|
| `GDRIVE_CREDENTIALS_FILE` | sim (p/ ativar) | — | Caminho do JSON da Service Account |
| `GDRIVE_FOLDER_ID` | sim (p/ ativar) | — | ID da pasta do Drive compartilhada com a SA |
| `GDRIVE_KEEP` | não | `30` | Quantos backups manter no Drive (rotação) |

Se `GDRIVE_CREDENTIALS_FILE` **ou** `GDRIVE_FOLDER_ID` faltar, o envio ao Drive
fica desligado e só o backup local roda (comportamento anterior).

---

## Rotação no Drive

Depois de cada upload, o app mantém os `GDRIVE_KEEP` backups mais recentes na
pasta e apaga os mais antigos (permanentemente, sem passar pela Lixeira, para não
acumular cota).

**Segurança**: a rotação só apaga arquivos com o prefixo `biblioteca-` **dentro
da pasta configurada**. Nunca varre o Drive inteiro nem toca em outros arquivos
do gestor.

---

## Resiliência

Uma falha no envio ao Drive (rede fora, credencial inválida) é **registrada nos
logs** mas **não derruba o backup local** — a cópia em `data/backups/` continua
sendo criada normalmente. O envio é tentado de novo no próximo ciclo de backup.

---

## Segurança da credencial

- O JSON é uma **chave privada** — trate como segredo. Nunca commite.
- Se vazar, **revogue** a chave no Console (aba Chaves da Service Account) e gere
  outra. Isso não afeta a conta pessoal do gestor.
- O gestor pode **descompartilhar** a pasta a qualquer momento para cortar o
  acesso da SA.
