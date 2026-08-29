import time
from nicegui import ui, app
import auth

ACCENT = "#89b4fa"


def build_login():
    ui.query("body").style("background-color: #1e1e2e")

    # Já autenticado: manda direto para a home
    if app.storage.user.get("authenticated"):
        ui.navigate.to("/")
        return

    def try_login():
        blocked = auth.seconds_until_unblocked(user.value or "")
        if blocked > 0:
            ui.notify(f"Muitas tentativas. Tente novamente em {blocked}s.", type="warning")
            return
        if auth.verify_credentials(user.value, password.value):
            app.storage.user.update({
                "authenticated": True,
                "username": user.value,
                "login_at": time.time(),
            })
            ui.navigate.to("/")
        else:
            remaining = auth.seconds_until_unblocked(user.value or "")
            if remaining > 0:
                ui.notify(f"Muitas tentativas. Bloqueado por {remaining}s.", type="negative")
            else:
                ui.notify("Usuário ou senha inválidos", type="negative")
            password.value = ""

    # Layout centralizado que continua acessível em telas pequenas (com scroll)
    with ui.column().classes("w-full items-center justify-center gap-4") \
            .style("min-height: 100vh; padding: 24px"):
        ui.label("🔒 Biblioteca SECRI").classes("text-2xl font-bold").style(f"color: {ACCENT}")
        with ui.card().classes("w-full").style("max-width: 320px; background-color: #2a2a3e"):
            ui.label("Entrar").classes("text-lg font-bold").style(f"color: {ACCENT}")
            user = ui.input("Usuário").props("outlined dense").classes("w-full")
            password = ui.input("Senha", password=True, password_toggle_button=True) \
                .props("outlined dense").classes("w-full")
            password.on("keydown.enter", try_login)
            user.on("keydown.enter", try_login)
            ui.button("Entrar", on_click=try_login).props("color=primary").classes("w-full")
