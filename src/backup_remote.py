"""Envio off-site dos backups para o Google Drive via Service Account.

Objetivo: tirar os backups da máquina local (proteção contra perda de disco).
Reaproveita o backup consistente gerado por `backup.py` e apenas faz o upload
para uma pasta do Drive compartilhada com a Service Account, aplicando a mesma
ideia de rotação (mantém os N mais recentes).

Autenticação: Service Account (conta de robô, não expira, sem login
interativo). O JSON de credencial é montado como secret e apontado por env.
A Service Account não tem cota própria de Drive, por isso o upload é sempre
DENTRO de uma pasta que o gestor compartilhou com o e-mail da SA (o arquivo
conta na cota do gestor). Ver docs/GOOGLE-DRIVE-BACKUP.md.

Ativação (opt-in): só faz algo se AMBAS as variáveis existirem:

    GDRIVE_CREDENTIALS_FILE  caminho do JSON da Service Account
    GDRIVE_FOLDER_ID         ID da pasta do Drive (compartilhada com a SA)

Config opcional:
    GDRIVE_KEEP              quantos backups manter no Drive (default: 30)

Segurança da rotação: só remove arquivos com o prefixo `biblioteca-` DENTRO da
pasta configurada. Nunca varre o Drive inteiro nem toca em outros arquivos.
"""
import os

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_PREFIX = "biblioteca-"
_MIME_DB = "application/x-sqlite3"


# ------------------------------ config helpers -----------------------------
def credentials_file() -> str | None:
    return os.environ.get("GDRIVE_CREDENTIALS_FILE") or None


def folder_id() -> str | None:
    return os.environ.get("GDRIVE_FOLDER_ID") or None


def _keep() -> int:
    return int(os.environ.get("GDRIVE_KEEP", "30"))


def is_configured() -> bool:
    """True se o envio para o Drive está habilitado (credencial + pasta)."""
    return bool(credentials_file() and folder_id())


# ------------------------------ Drive client -------------------------------
def _build_service():
    """Cria o cliente da Drive API autenticado como Service Account.

    Import preguiçoso das libs do Google para o app não exigir a dependência
    quando o envio ao Drive não está configurado.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        credentials_file(), scopes=_SCOPES)
    # cache_discovery=False evita warnings/IO de cache em ambiente sem escrita.
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# --------------------------------- upload ----------------------------------
def upload_to_drive(path: str, service=None) -> str:
    """Sobe o arquivo `path` para a pasta configurada. Retorna o file id.

    `service` pode ser injetado (testes). Se ausente, cria um real.
    """
    from googleapiclient.http import MediaFileUpload

    svc = service or _build_service()
    metadata = {"name": os.path.basename(path), "parents": [folder_id()]}
    media = MediaFileUpload(path, mimetype=_MIME_DB, resumable=False)
    created = svc.files().create(
        body=metadata, media_body=media, fields="id").execute()
    return created["id"]


# -------------------------------- rotation ---------------------------------
def _list_remote(svc) -> list[dict]:
    """Lista os backups `biblioteca-*` na pasta, mais recentes primeiro.

    Ordena por `name desc` — o nome carrega o timestamp
    (biblioteca-YYYYMMDD-HHMMSS.db), então a ordem por nome == ordem temporal.
    """
    query = (
        f"'{folder_id()}' in parents and trashed = false "
        f"and name contains '{_PREFIX}'"
    )
    files: list[dict] = []
    page_token = None
    while True:
        resp = svc.files().list(
            q=query,
            fields="nextPageToken, files(id, name)",
            orderBy="name desc",
            pageSize=100,
            pageToken=page_token,
        ).execute()
        # Guarda só os que realmente começam com o prefixo (contains é amplo).
        files.extend(f for f in resp.get("files", [])
                     if f.get("name", "").startswith(_PREFIX))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def rotate_drive(keep: int | None = None, service=None) -> list[str]:
    """Remove os backups mais antigos na pasta, mantendo os `keep` recentes.

    Retorna a lista de nomes removidos. Deleta permanentemente (não vai para a
    Lixeira) para não acumular cota. Só toca em arquivos `biblioteca-*` dentro
    da pasta configurada.
    """
    keep = _keep() if keep is None else keep
    svc = service or _build_service()
    files = _list_remote(svc)  # mais recentes primeiro
    to_remove = files[keep:] if keep > 0 else files
    removed: list[str] = []
    for f in to_remove:
        try:
            svc.files().delete(fileId=f["id"]).execute()
            removed.append(f["name"])
        except Exception:
            pass  # falha ao apagar um não impede os demais
    return removed


# --------------------------------- public ----------------------------------
def send_backup(path: str) -> str | None:
    """Sobe `path` para o Drive e aplica a rotação remota.

    No-op (retorna None) se o envio não estiver configurado. Levanta exceção
    em falha real de upload — o chamador (run_backup) trata/loga, mantendo o
    backup local intacto.
    """
    if not is_configured():
        return None
    svc = _build_service()
    file_id = upload_to_drive(path, service=svc)
    rotate_drive(service=svc)
    return file_id
