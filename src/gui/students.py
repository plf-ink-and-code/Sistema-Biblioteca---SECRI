from nicegui import ui, app
import services
from gui import theme


class StudentsPage:
    def build(self):
        theme.apply()
        p = theme.palette()
        with ui.column().classes("w-full max-w-4xl mx-auto") \
                .style(f"padding: 1rem; gap: {theme.GAP['lg']}"):
            with ui.row().classes("w-full items-center").style(f"gap: {theme.GAP['md']}"):
                ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/")) \
                    .props("flat round").tooltip("Voltar")
                ui.icon("school").style(f"color: {p['primary']}; font-size: 1.6rem;")
                ui.label("Cadastro de Alunos").style(
                    f"color: {p['text']}; font-size: 1.5rem; font-weight: 700;")
                ui.space()
                theme.theme_toggle()
                ui.button("Novo Aluno", icon="person_add", on_click=self._dialog_add) \
                    .props("color=primary unelevated")

            columns = [
                {"name": "name", "label": "Nome", "field": "name", "align": "left", "sortable": True},
                {"name": "email", "label": "E-mail", "field": "email", "align": "left", "sortable": True},
                {"name": "actions", "label": "Ações", "field": "actions", "align": "center"},
            ]
            self.table = ui.table(columns=columns, rows=[], row_key="id",
                                  pagination={"rowsPerPage": 15}).classes("sb-card w-full")
            self.table.add_slot("body-cell-actions", """
                <q-td :props="props">
                    <q-btn flat dense round icon="edit" @click="$parent.$emit('edit', props.row)" />
                    <q-btn flat dense round icon="delete" color="negative" @click="$parent.$emit('delete', props.row)" />
                </q-td>
            """)
            self.table.add_slot("no-data", """
                <div class="full-width row flex-center q-pa-lg text-grey">
                    <q-icon name="group_off" size="24px" class="q-mr-sm" />
                    Nenhum aluno cadastrado.
                </div>
            """)
            self.table.on("edit", self._edit_student)
            self.table.on("delete", self._delete_student)
            self._refresh()

    def _refresh(self):
        self.table.rows = [{"id": s["id"], "name": s["name"], "email": s.get("email") or ""}
                           for s in services.list_students()]
        self.table.update()

    def _dialog_add(self):
        self._student_dialog(title="Novo Aluno", success_msg="Aluno cadastrado ✓",
                             on_save=lambda name, email: services.add_student(name, email, None))

    def _edit_student(self, e):
        row = e.args
        self._student_dialog(title="Editar Aluno", success_msg="Aluno atualizado ✓",
                             name=row["name"], email=row["email"],
                             on_save=lambda name, email: services.edit_student(row["id"], name, email, None))

    def _student_dialog(self, title, on_save, success_msg, name="", email=""):
        dlg, body, footer = theme.dialog_shell(title, width="380px")
        with body:
            name_in = ui.input("Nome *", value=name).props("outlined dense").classes("w-full")
            email_in = ui.input("E-mail", value=email).props("outlined dense type=email").classes("w-full")

        def save():
            if not name_in.value.strip():
                ui.notify("Nome obrigatório", type="negative")
                return
            on_save(name_in.value.strip(), email_in.value.strip())
            dlg.close()
            self._refresh()
            ui.notify(success_msg, type="positive")
            self._audit(f"{title}: {name_in.value.strip()}")

        with footer:
            ui.button("Cancelar", on_click=dlg.close).props("flat")
            ui.button("Salvar", on_click=save).props("color=primary unelevated")
        dlg.open()

    def _delete_student(self, e):
        row = e.args
        dlg, body, footer = theme.dialog_shell("Remover Aluno", width="360px")
        with body:
            ui.label(f"Remover {row['name']}?")
        def confirm():
            services.remove_student(row["id"])
            dlg.close()
            self._refresh()
            self._audit(f"Removeu aluno: {row['name']}")
        with footer:
            ui.button("Cancelar", on_click=dlg.close).props("flat")
            ui.button("Remover", on_click=confirm).props("color=negative unelevated")
        dlg.open()

    def _audit(self, detail):
        try:
            username = app.storage.user.get("username", "?")
            services.log_action("aluno", detail=detail, username=username)
        except Exception:
            pass
