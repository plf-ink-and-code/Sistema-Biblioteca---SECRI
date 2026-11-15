from nicegui import ui, run, app
from datetime import datetime
import services
import notifier
from gui import theme
from gui.dialogs import (dialog_add, dialog_edit, dialog_remove,
                         dialog_loan, dialog_return, dialog_renew, dialog_reports)


class LibraryPage:
    def __init__(self):
        self.selected_id = None
        self.current_initial = None

    def build(self):
        theme.apply()
        p = theme.palette()
        with ui.column().classes("w-full mx-auto") \
                .style(f"padding: 1rem 1.5rem; gap: {theme.GAP['lg']}; max-width: 1800px;"):

            # ---- Header -------------------------------------------------
            with theme.page_header("Biblioteca SECRI", icon="local_library"):
                ui.space()
                username = app.storage.user.get("username", "")
                if username:
                    ui.label(f"👤 {username}").style(
                        f"color: {p['text_muted']}; font-size: 0.9rem;")
                theme.theme_toggle()
                ui.button("Alunos", icon="school",
                          on_click=lambda: ui.navigate.to("/alunos")).props("flat")
                ui.button(icon="logout", on_click=self._logout) \
                    .props("flat round").tooltip("Sair")

            # ---- Dashboard (cards clicáveis, destaca o ativo) -----------
            self.dash_container = ui.row().classes("w-full").style(f"gap: {theme.GAP['lg']}")
            self._build_dashboard()

            # ---- Barra de ações + busca ---------------------------------
            with theme.section_card():
                with ui.row().classes("w-full items-center flex-wrap") \
                        .style(f"gap: {theme.GAP['sm']}"):
                    ui.button("Adicionar", icon="add", on_click=self._add) \
                        .props("color=primary unelevated")
                    ui.button("Editar", icon="edit", on_click=self._edit).props("flat")
                    ui.button("Remover", icon="delete", on_click=self._remove) \
                        .props("flat color=negative")
                    ui.separator().props("vertical").classes("h-8")
                    ui.button("Alugar", icon="outbox", on_click=self._loan) \
                        .props("color=accent unelevated")
                    ui.button("Devolver", icon="inbox", on_click=self._return) \
                        .props("flat color=positive")
                    ui.button("Renovar", icon="autorenew", on_click=self._renew) \
                        .props("flat color=warning")
                    ui.separator().props("vertical").classes("h-8")
                    ui.button("Relatórios", icon="assessment",
                              on_click=self._reports).props("flat")
                    self.btn_notify = ui.button("Notificar", icon="mail",
                                                on_click=self._notify_manager) \
                        .props("flat color=warning")
                    ui.space()
                    self.search_input = ui.input(placeholder="Buscar título, autor...") \
                        .props("dense outlined clearable").classes("w-56")
                    self.search_input.on("keydown.enter", self._search)
                    self.search_input.on("clear", lambda: self._refresh())
                    ui.button(icon="search", on_click=self._search).props("flat dense")
                    ui.button(icon="refresh", on_click=lambda: self._refresh()) \
                        .props("flat dense").tooltip("Recarregar")

            # ---- Filtros (categoria/status) + A-Z -----------------------
            with theme.section_card():
                with ui.row().classes("w-full items-center flex-wrap") \
                        .style(f"gap: {theme.GAP['lg']}"):
                    cats = ["Todas"] + services.list_categories()
                    self.filter_cat = ui.select(cats, value="Todas", label="Categoria",
                                                on_change=self._apply_filters) \
                        .props("dense outlined").classes("w-48")
                    self.filter_status = ui.select(
                        ["Todos", "Disponíveis", "Esgotados", "Atrasados"],
                        value="Todos", label="Status",
                        on_change=self._apply_filters).props("dense outlined").classes("w-40")
                    ui.space()
                    self.label_results = ui.label("").style(
                        f"color: {p['text_muted']}; font-size: 0.85rem;")
                # Toggle alfabético compacto
                options = ["Todos", "0-9"] + [chr(c) for c in range(ord("A"), ord("Z") + 1)]
                self.alpha = ui.toggle(options, value="Todos",
                                       on_change=self._on_alpha) \
                    .props("no-caps dense unelevated toggle-color=primary") \
                    .style("flex-wrap: wrap;")

            # ---- Tabela -------------------------------------------------
            columns = [
                {"name": "code", "label": "Nº", "field": "code", "align": "center", "sortable": True},
                {"name": "title", "label": "Título", "field": "title", "align": "left", "sortable": True},
                {"name": "copies_label", "label": "Disponível", "field": "copies_label", "align": "center", "sortable": True},
                {"name": "status", "label": "Status", "field": "status", "align": "center", "sortable": True},
                {"name": "author", "label": "Autor", "field": "author", "align": "left", "sortable": True},
                {"name": "category", "label": "Categoria", "field": "category", "align": "left", "sortable": True},
                {"name": "person", "label": "Aluno", "field": "person", "align": "left", "sortable": True},
            ]
            self.table = ui.table(columns=columns, rows=[], row_key="id",
                                  pagination={"rowsPerPage": 20}).classes("sb-card w-full")
            self.table.on("rowClick", self._on_row_click)
            self.table.add_slot("body-cell-status", """
                <q-td :props="props">
                    <q-badge :color="props.row.status === 'Atrasado' ? 'negative'
                              : props.row.status === 'Esgotado' ? 'warning' : 'positive'"
                             :label="props.row.status" outline />
                </q-td>
            """)
            self.table.add_slot("no-data", """
                <div class="full-width row flex-center q-pa-lg text-grey">
                    <q-icon name="inbox" size="24px" class="q-mr-sm" />
                    Nenhum livro encontrado.
                </div>
            """)
            ui.add_css("""
                .selected-row { outline: 2px solid var(--sb-primary); outline-offset: -2px; }
                .q-table tbody tr { cursor: pointer; }
            """)

        self._refresh()

    # ---- helpers ---------------------------------------------------------
    def _logout(self):
        app.storage.user.clear()
        ui.navigate.to("/login")

    def _on_row_click(self, e):
        try:
            row = e.args[1] if isinstance(e.args, list) else e.args
            self.selected_id = row.get("id") if isinstance(row, dict) else None
        except (IndexError, KeyError, TypeError):
            self.selected_id = None
        idx = e.args[2] if isinstance(e.args, list) and len(e.args) > 2 else -1
        ui.run_javascript(f'''
            document.querySelectorAll(".q-table tbody tr").forEach(r => r.classList.remove("selected-row"));
            const rows = document.querySelectorAll(".q-table tbody tr");
            if ({idx} >= 0 && rows[{idx}]) rows[{idx}].classList.add("selected-row");
        ''')

    def _get_selected(self):
        if not self.selected_id:
            ui.notify("Selecione um livro (clique na linha).", type="warning")
            return None
        return self.selected_id

    def _set_event(self, msg):
        ui.notify(msg, type="positive", position="bottom-right")

    def _on_done(self, msg):
        self._refresh()
        self._set_event(msg)
        try:
            username = app.storage.user.get("username", "?")
            services.log_action("livro", detail=msg, username=username)
        except Exception:
            pass

    def _refresh(self, books=None):
        rows = services.books_with_status(books, initial=self.current_initial)
        self.table.rows = rows
        self.table.update()
        self.label_results.text = f"{len(rows)} livros"

    def _build_dashboard(self):
        """(Re)desenha os cards do dashboard destacando o filtro de status ativo."""
        stats = services.dashboard_stats()
        active = getattr(self, "filter_status", None)
        active = active.value if active is not None else "Todos"
        self.dash_container.clear()
        with self.dash_container:
            theme.stat_card("Títulos", f"{stats['total']:,}".replace(",", "."),
                            "primary", "menu_book",
                            on_click=lambda: self._quick_filter("Todos"),
                            active=(active == "Todos"))
            theme.stat_card("Exemplares",
                            f"{stats.get('exemplars', stats['total']):,}".replace(",", "."),
                            "info", "inventory_2")
            theme.stat_card("Disponíveis", f"{stats['available']:,}".replace(",", "."),
                            "positive", "check_circle",
                            on_click=lambda: self._quick_filter("Disponíveis"),
                            active=(active == "Disponíveis"))
            theme.stat_card("Emprestados", str(stats["loaned"]), "warning",
                            "outbox", on_click=lambda: self._quick_filter("Esgotados"),
                            active=(active == "Esgotados"))
            theme.stat_card("Atrasados", str(stats["overdue"]), "negative",
                            "warning", on_click=lambda: self._quick_filter("Atrasados"),
                            active=(active == "Atrasados"))
            theme.stat_card("Devoluções/mês", str(stats["returns_month"]),
                            "secondary", "autorenew")

    def _on_alpha(self, _=None):
        self.current_initial = None if self.alpha.value == "Todos" else self.alpha.value
        self._apply_filters()

    def _quick_filter(self, status):
        """Atalho dos cards do dashboard."""
        self.filter_status.value = status if status != "Todos" else "Todos"
        self.filter_cat.value = "Todas"
        self._apply_filters()

    def _apply_filters(self, _=None):
        cat = self.filter_cat.value
        status = self.filter_status.value
        rows = services.books_with_status(
            category=None if cat == "Todas" else cat,
            initial=self.current_initial,
        )
        if status == "Disponíveis":
            rows = [r for r in rows if r["status"] == "Disponível"]
        elif status == "Esgotados":
            rows = [r for r in rows if r["status"] == "Esgotado"]
        elif status == "Atrasados":
            rows = [r for r in rows if r["status"] == "Atrasado"]
        self.table.rows = rows
        self.table.update()
        self.label_results.text = f"{len(rows)} livros"
        self._build_dashboard()

    def _search(self, _=None):
        term = self.search_input.value.strip() if self.search_input.value else ""
        self.filter_cat.value = "Todas"
        self.filter_status.value = "Todos"
        self.current_initial = None
        self.alpha.value = "Todos"
        self._refresh(services.search_books(term)) if term else self._refresh()

    # ---- ações -----------------------------------------------------------
    def _add(self):
        dialog_add(self._on_done)

    def _edit(self):
        book_id = self._get_selected()
        if book_id:
            dialog_edit(book_id, self._on_done)

    def _remove(self):
        book_id = self._get_selected()
        if book_id:
            dialog_remove(book_id, lambda msg: (setattr(self, 'selected_id', None), self._on_done(msg)))

    def _loan(self):
        book_id = self._get_selected()
        if book_id:
            dialog_loan(book_id, self._on_done)

    def _return(self):
        book_id = self._get_selected()
        if book_id:
            dialog_return(book_id, self._on_done)

    def _renew(self):
        book_id = self._get_selected()
        if book_id:
            dialog_renew(book_id, self._on_done)

    def _reports(self):
        dialog_reports(self._set_event)

    async def _notify_manager(self):
        self.btn_notify.props("loading disable")
        try:
            result = await run.io_bound(notifier.send_manager_notification)
            self._set_event(result)
            ui.notify(result, type="positive")
        except Exception as e:
            ui.notify(f"Falha: {e}", type="negative")
        finally:
            self.btn_notify.props(remove="loading disable")
