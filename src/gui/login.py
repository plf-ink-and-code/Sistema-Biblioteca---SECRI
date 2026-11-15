import time
from nicegui import ui, app
import auth
from gui import theme


def build_login():
    theme.apply()
    p = theme.palette()

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

    # toggle de tema no canto superior direito
    with ui.row().classes("w-full justify-end").style("padding: 12px;"):
        theme.theme_toggle()

    with ui.column().classes("w-full items-center justify-center") \
            .style(f"min-height: 90vh; gap: {theme.GAP['lg']}; padding: 24px;"):
        with ui.column().classes("items-center").style(f"gap: {theme.GAP['sm']}"):
            ui.icon("local_library").style(
                f"color: {p['primary']}; font-size: 3rem;")
            ui.label("Biblioteca SECRI").style(
                f"color: {p['text']}; font-size: 1.6rem; font-weight: 700;")
            ui.label("Gestão de acervo e empréstimos").style(
                f"color: {p['text_muted']}; font-size: 0.9rem;")

        with ui.card().classes("sb-card").style(
                f"width: 100%; max-width: 340px; padding: 1.5rem; gap: {theme.GAP['md']};"):
            ui.label("Entrar").style(
                f"color: {p['text']}; font-size: 1.1rem; font-weight: 600;")
            user = ui.input("Usuário").props("outlined dense").classes("w-full")
            password = ui.input("Senha", password=True, password_toggle_button=True) \
                .props("outlined dense").classes("w-full")
            password.on("keydown.enter", try_login)
            user.on("keydown.enter", try_login)
            ui.button("Entrar", on_click=try_login).props("color=primary unelevated") \
                .classes("w-full")
