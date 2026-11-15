from nicegui import ui
import services
from gui import theme
from gui.pdf import export_pdf


def dialog_add(on_done):
    dlg, body, footer = theme.dialog_shell("Adicionar Livro")
    with body:
        code = ui.input("Nº").props("outlined dense").classes("w-full")
        title = ui.input("Título *").props("outlined dense").classes("w-full")
        author = ui.input("Autor *").props("outlined dense").classes("w-full")
        category = ui.input("Categoria").props("outlined dense").classes("w-full")
        year = ui.input("Ano").props("outlined dense").classes("w-full")
        copies = ui.number("Cópias (exemplares)", value=1, min=1, format="%d") \
            .props("outlined dense").classes("w-full")

    def save():
        if not title.value.strip() or not author.value.strip():
            ui.notify("Título e Autor obrigatórios", type="negative")
            return
        y = int(year.value) if year.value.strip().isdigit() else None
        n = int(copies.value) if copies.value and int(copies.value) >= 1 else 1
        services.add_book(title.value.strip(), author.value.strip(),
                          category.value.strip(), y, code.value.strip(), n)
        dlg.close()
        on_done("Livro adicionado")

    with footer:
        ui.button("Cancelar", on_click=dlg.close).props("flat")
        ui.button("Salvar", on_click=save).props("color=primary unelevated")
    dlg.open()


def dialog_edit(book_id, on_done):
    book = services.get_book(book_id)
    if not book:
        return
    dlg, body, footer = theme.dialog_shell("Editar Livro")
    with body:
        code = ui.input("Nº", value=book["code"] or "").props("outlined dense").classes("w-full")
        title = ui.input("Título *", value=book["title"]).props("outlined dense").classes("w-full")
        author = ui.input("Autor *", value=book["author"]).props("outlined dense").classes("w-full")
        category = ui.input("Categoria", value=book["category"] or "").props("outlined dense").classes("w-full")
        year = ui.input("Ano", value=str(book["year"]) if book["year"] else "").props("outlined dense").classes("w-full")
        copies = ui.number("Cópias (exemplares)", value=book.get("copies", 1) or 1,
                           min=1, format="%d").props("outlined dense").classes("w-full")

    def save():
        if not title.value.strip() or not author.value.strip():
            ui.notify("Título e Autor obrigatórios", type="negative")
            return
        y = int(year.value) if year.value.strip().isdigit() else None
        n = int(copies.value) if copies.value and int(copies.value) >= 1 else 1
        services.edit_book(book_id, title.value.strip(), author.value.strip(),
                           category.value.strip(), y, code.value.strip(), n)
        dlg.close()
        on_done("Livro editado")

    with footer:
        ui.button("Cancelar", on_click=dlg.close).props("flat")
        ui.button("Salvar", on_click=save).props("color=primary unelevated")
    dlg.open()


def dialog_remove(book_id, on_done):
    dlg, body, footer = theme.dialog_shell("Remover Livro", width="380px")
    with body:
        ui.label("Remover este livro e todo o seu histórico de empréstimos?")
    def confirm():
        services.remove_book(book_id)
        dlg.close()
        on_done("Livro removido")
    with footer:
        ui.button("Cancelar", on_click=dlg.close).props("flat")
        ui.button("Remover", on_click=confirm).props("color=negative unelevated")
    dlg.open()


def dialog_loan(book_id, on_done):
    book = services.get_book(book_id)
    if not book:
        return
    avail = services.available_count(book_id)
    copies = book.get("copies", 1) or 1
    if avail <= 0:
        ui.notify("Não há exemplares disponíveis (todas as cópias emprestadas).",
                  type="warning")
        return

    students = services.list_students()
    student_names = [s["name"] for s in students]
    student_map = {s["name"]: s.get("email") or "" for s in students}
    p = theme.palette()

    dlg, body, footer = theme.dialog_shell("Alugar Livro")
    with body:
        ui.label(f"📦 {avail} de {copies} exemplares disponíveis").style(
            f"color: {p['positive']}; font-weight: 500;")
        person = ui.input("Nome *", autocomplete=student_names) \
            .props("outlined dense").classes("w-full")
        email = ui.input("E-mail").props("outlined dense type=email").classes("w-full")
        def fill_email():
            if person.value in student_map and student_map[person.value]:
                email.value = student_map[person.value]
        person.on("blur", fill_email)
        deadline = ui.input("Devolução (dd/mm/aaaa)").props('outlined dense mask="##/##/####"').classes("w-full")

    def confirm():
        if not person.value.strip():
            ui.notify("Informe o nome", type="negative")
            return
        deadline_iso = None
        if deadline.value.strip():
            try:
                deadline_iso = services.parse_date_br(deadline.value.strip(), must_be_future=True)
            except ValueError as e:
                ui.notify(str(e), type="negative")
                return
        em = email.value.strip() or None
        if em and not services.validate_email(em):
            ui.notify("E-mail inválido", type="negative")
            return
        try:
            services.loan_book(book_id, person.value.strip(), deadline_iso, em)
        except ValueError as e:
            ui.notify(str(e), type="negative")
            return
        dlg.close()
        on_done(f"Emprestado para {person.value.strip()}")

    with footer:
        ui.button("Cancelar", on_click=dlg.close).props("flat")
        ui.button("Confirmar", on_click=confirm).props("color=accent unelevated")
    dlg.open()


def dialog_return(book_id, on_done):
    loan = services.active_loan(book_id)
    if not loan:
        ui.notify("Livro não está emprestado", type="warning")
        return
    dlg, body, footer = theme.dialog_shell("Devolver Livro", width="380px")
    with body:
        ui.label(f'Confirmar devolução de "{services.get_book(book_id)["title"]}"?')
        ui.label(f"Aluno: {loan['person']}").style("font-size: 0.9rem;")
    def confirm():
        services.return_book(book_id)
        dlg.close()
        on_done("Livro devolvido")
    with footer:
        ui.button("Cancelar", on_click=dlg.close).props("flat")
        ui.button("Devolver", on_click=confirm).props("color=positive unelevated")
    dlg.open()


def dialog_renew(book_id, on_done):
    loan = services.active_loan(book_id)
    if not loan:
        ui.notify("Este livro não está emprestado", type="warning")
        return
    dlg, body, footer = theme.dialog_shell("Renovar Empréstimo", width="380px")
    with body:
        ui.label(f"Aluno: {loan['person']}")
        ui.label(f"Prazo atual: {services.format_date(loan.get('deadline_date')) or 'Sem prazo'}") \
            .style("font-size: 0.9rem;")
        new_deadline = ui.input("Novo prazo (dd/mm/aaaa)") \
            .props('outlined dense mask="##/##/####"').classes("w-full")

    def confirm():
        if not new_deadline.value.strip():
            ui.notify("Informe a nova data", type="negative")
            return
        try:
            iso = services.parse_date_br(new_deadline.value.strip(), must_be_future=True)
            services.renew_loan(book_id, iso)
        except ValueError as e:
            ui.notify(str(e), type="negative")
            return
        dlg.close()
        on_done("Empréstimo renovado")

    with footer:
        ui.button("Cancelar", on_click=dlg.close).props("flat")
        ui.button("Renovar", on_click=confirm).props("color=warning unelevated")
    dlg.open()


def dialog_reports(on_event):
    dlg, body, footer = theme.dialog_shell("Relatórios", width="680px", height="80vh")
    body.style("overflow-x: hidden;")
    with body:
        with ui.tabs().classes("w-full") as tabs:
            tab_b = ui.tab("Top Livros")
            tab_p = ui.tab("Top Alunos")
        with ui.tab_panels(tabs, value=tab_b).classes("w-full").style("width: 100%;"):
            with ui.tab_panel(tab_b).style("padding: 0;"):
                cols = [
                    {"name": "title", "label": "Título", "field": "title", "align": "left",
                     "style": "max-width: 360px; white-space: normal;"},
                    {"name": "author", "label": "Autor", "field": "author", "align": "left",
                     "style": "max-width: 160px; white-space: normal;"},
                    {"name": "total", "label": "Qtd", "field": "total", "align": "center", "sortable": True},
                ]
                rows = [{"title": r["title"], "author": r["author"], "total": r["total"]} for r in services.top_loaned_books()]
                ui.table(columns=cols, rows=rows).classes("w-full").style("width: 100%;")
            with ui.tab_panel(tab_p).style("padding: 0;"):
                cols = [{"name": "person", "label": "Aluno", "field": "person", "align": "left"},
                        {"name": "total", "label": "Qtd", "field": "total", "align": "center", "sortable": True}]
                rows = [{"person": r["person"], "total": r["total"]} for r in services.top_borrowers()]
                ui.table(columns=cols, rows=rows).classes("w-full").style("width: 100%;")
    with footer:
        ui.button("Exportar PDF", icon="picture_as_pdf",
                  on_click=lambda: (export_pdf(), on_event("PDF exportado"))).props("flat")
        ui.button("Fechar", on_click=dlg.close).props("flat")
    dlg.open()
