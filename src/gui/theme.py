"""
Tema central da UI (Sistema Biblioteca SECRI).

Fonte ÚNICA de verdade para cores, tokens e componentes reutilizáveis.
Suporta DARK (Catppuccin refinado) e LIGHT (SaaS teal/limpo), com toggle
persistido em app.storage.user["theme"].

Regras NiceGUI seguidas (evitam bugs reais):
- NUNCA usar classes Tailwind gap-* (bug #2171 no Ubuntu). Usar style("gap: Xrem").
- Botões de ação em diálogos ficam FIXOS no rodapé (sticky), sempre visíveis.
- Paleta centralizada via ui.colors(...), não cores hardcoded espalhadas.
- Ícones outline; badges sutis (fundo claro + texto da cor + borda fina).
"""
from nicegui import app, ui

# ---------------------------------------------------------------------------
# Paletas
# ---------------------------------------------------------------------------
DARK = {
    "primary": "#89b4fa",   # azul Catppuccin
    "secondary": "#94e2d5",
    "accent": "#cba6f7",
    "positive": "#a6e3a1",
    "negative": "#f38ba8",
    "warning": "#f9e2af",
    "info": "#89dceb",
    "dark": "#1e1e2e",      # fundo página
    "surface": "#2a2a3e",   # cards
    "surface2": "#313244",  # hover / inputs
    "border": "#45475a",
    "text": "#cdd6f4",
    "text_muted": "#9399b2",
}

LIGHT = {
    "primary": "#18b69b",   # teal (SaaS design system)
    "secondary": "#0091ff",
    "accent": "#30a46c",
    "positive": "#30a46c",
    "negative": "#ca244d",
    "warning": "#f76808",
    "info": "#0091ff",
    "dark": "#f6f8f7",      # fundo página (claro)
    "surface": "#ffffff",   # cards
    "surface2": "#f2f4f2",  # hover / inputs
    "border": "#e2e6e2",
    "text": "#141e12",
    "text_muted": "#6b716a",
}

# Tokens compartilhados
RADIUS = "10px"
RADIUS_SM = "6px"
SHADOW = "0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)"
SHADOW_LG = "0 8px 24px rgba(0,0,0,0.12)"
FONT = "'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"

# Espaçamento (sempre inline — nunca gap-* do Tailwind)
GAP = {"xs": "0.25rem", "sm": "0.5rem", "md": "0.75rem", "lg": "1rem", "xl": "1.5rem"}


def is_dark() -> bool:
    try:
        return app.storage.user.get("theme", "light") != "light"
    except Exception:
        return True


def palette() -> dict:
    return DARK if is_dark() else LIGHT


def toggle_theme():
    """Alterna dark<->light e recarrega a página para reaplicar a paleta."""
    current = app.storage.user.get("theme", "light")
    app.storage.user["theme"] = "light" if current == "dark" else "dark"
    ui.navigate.reload()


# ---------------------------------------------------------------------------
# Aplicação do tema (chamar no topo de cada página)
# ---------------------------------------------------------------------------
def apply(dark: bool | None = None):
    """Aplica paleta via ui.colors, injeta CSS global e seta o fundo da página.

    Deve ser chamado no início do build de cada página.
    """
    if dark is None:
        dark = is_dark()
    p = DARK if dark else LIGHT

    ui.colors(
        primary=p["primary"], secondary=p["secondary"], accent=p["accent"],
        positive=p["positive"], negative=p["negative"], warning=p["warning"],
        info=p["info"], dark=p["dark"],
    )
    # dark mode do Quasar acompanha o tema
    try:
        ui.dark_mode(dark)
    except Exception:
        pass

    ui.query("body").style(
        f"background-color: {p['dark']}; color: {p['text']}; font-family: {FONT};"
    )

    ui.add_head_html(
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap' rel='stylesheet'>"
    )
    ui.add_css(f"""
        :root {{ --sb-surface: {p['surface']}; --sb-surface2: {p['surface2']};
                 --sb-border: {p['border']}; --sb-text: {p['text']};
                 --sb-text-muted: {p['text_muted']}; --sb-primary: {p['primary']}; }}
        body {{ font-family: {FONT}; }}
        ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
        ::-webkit-scrollbar-thumb {{ background: {p['border']}; border-radius: 8px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        .sb-card {{ background: {p['surface']}; border: 1px solid {p['border']};
                    border-radius: {RADIUS}; box-shadow: {SHADOW}; }}
        .sb-stat {{ transition: transform 120ms ease, box-shadow 120ms ease; cursor: pointer; }}
        .sb-stat:hover {{ transform: translateY(-2px); box-shadow: {SHADOW_LG}; }}
        .q-table tbody tr {{ transition: background-color 120ms ease; }}
        .q-table tbody tr:hover {{ background: {p['surface2']} !important; }}
        .q-table thead th {{ font-weight: 600; color: {p['text_muted']}; }}
    """)


# ---------------------------------------------------------------------------
# Componentes reutilizáveis
# ---------------------------------------------------------------------------
def theme_toggle():
    """Botão de alternância dark/light para o header."""
    icon = "light_mode" if is_dark() else "dark_mode"
    return ui.button(icon=icon, on_click=toggle_theme).props("flat round") \
        .tooltip("Alternar tema claro/escuro")


def stat_card(title, value, color_key="primary", icon=None, on_click=None, active=False):
    """Card de métrica do dashboard (clicável quando on_click é dado).

    `active=True` destaca o card (borda + glow na cor) para indicar o filtro ativo.
    """
    p = palette()
    color = p.get(color_key, p["primary"])
    extra = ""
    if active:
        extra = (f"border: 2px solid {color}; box-shadow: 0 0 0 3px {color}33, {SHADOW_LG};")
    card = ui.card().classes("sb-card sb-stat flex-1").style(
        f"min-width: 150px; padding: 1rem; {extra}"
    )
    if on_click:
        card.on("click", on_click)
    with card:
        with ui.row().classes("items-center").style(f"gap: {GAP['sm']}"):
            if icon:
                ui.icon(icon).style(f"color: {color}; font-size: 1.4rem;")
            ui.label(title).style(f"color: {p['text_muted']}; font-size: 0.8rem;")
        ui.label(str(value)).style(
            f"color: {color}; font-size: 1.8rem; font-weight: 700; line-height: 1.1;"
        )
    return card


def section_card():
    """Container de seção (barra de ações, filtros, tabela)."""
    return ui.card().classes("sb-card w-full").style("padding: 1rem;")


def page_header(title, icon="menu_book"):
    """Cabeçalho de página com título + ícone; retorna a row p/ anexar ações."""
    p = palette()
    row = ui.row().classes("w-full items-center").style(f"gap: {GAP['md']}")
    with row:
        ui.icon(icon).style(f"color: {p['primary']}; font-size: 1.6rem;")
        ui.label(title).style(
            f"color: {p['text']}; font-size: 1.5rem; font-weight: 700;"
        )
    return row


def dialog_shell(title, width="440px", height=None):
    """Cria (dialog, card, body, footer) com rodapé FIXO (sticky).

    Uso:
        dlg, body, footer = theme.dialog_shell("Alugar Livro")
        with body: ...campos...
        with footer: ...botões...
        dlg.open()
    """
    p = palette()
    style = f"width: {width}; display: flex; flex-direction: column;"
    if height:
        style += f" height: {height};"
    dlg = ui.dialog()
    with dlg:
        card = ui.card().classes("sb-card").style(style + " padding: 0;")
        with card:
            ui.label(title).style(
                f"color: {p['primary']}; font-size: 1.1rem; font-weight: 600;"
                f" padding: 1rem 1rem 0 1rem;"
            )
            body = ui.column().style(
                f"padding: 1rem; gap: {GAP['md']}; flex: 1; overflow-y: auto;"
            )
            footer = ui.row().classes("justify-end").style(
                f"gap: {GAP['sm']}; padding: 0.75rem 1rem; position: sticky; bottom: 0;"
                f" background: {p['surface']}; border-top: 1px solid {p['border']};"
            )
    return dlg, body, footer
