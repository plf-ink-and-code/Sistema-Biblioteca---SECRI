from nicegui import ui, app
import services

ACCENT = "#89b4fa"


class StudentsPage:
    def build(self):
        ui.query("body").style("background-color: #1e1e2e")
        with ui.column().classes("w-full max-w-4xl mx-auto p-4 gap-4"):
            with ui.row().classes("w-full items-center"):
                ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props("flat")
                ui.label("🎓 Cadastro de Alunos").classes("text-2xl font-bold").style(f"color: {ACCENT}")
                ui.space()
                ui.button("+ Novo Aluno", on_click=self._dialog_add).props("color=primary")

            columns = [
                {"name": "name", "label": "Nome", "field": "name", "align": "left", "sortable": True},
                {"name": "email", "label": "E-mail", "field": "email", "align": "left", "sortable": True},
                {"name": "actions", "label": "Ações", "field": "actions", "align": "center"},
            ]
            self.table = ui.table(columns=columns, rows=[], row_key="id",
                                  pagination={"rowsPerPage": 15}).classes("w-full").style("background-color: #2a2a3e; color: #cdd6f4")
            self.table.add_slot("body-cell-actions", """
                <q-td :props="props">
                    <q-btn flat dense icon="edit" @click="$parent.$emit('edit', props.row)" />
                    <q-btn flat dense icon="delete" color="negative" @click="$parent.$emit('delete', props.row)" />
                </q-td>
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
        with ui.dialog() as dlg, ui.card().style("width: 380px"):
            ui.label(title).classes("text-lg font-bold").style(f"color: {ACCENT}")
            name_in = ui.input("Nome *", value=name)
            email_in = ui.input("E-mail", value=email).props("type=email")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dlg.close).props("flat")

                def save():
                    if not name_in.value.strip():
                        ui.notify("Nome obrigatório", type="negative")
                        return
                    on_save(name_in.value.strip(), email_in.value.strip())
                    dlg.close()
                    self._refresh()
                    ui.notify(success_msg, type="positive")
                    self._audit(f"{title}: {name_in.value.strip()}")

                ui.button("Salvar", on_click=save).props("color=primary")
        dlg.open()

    def _delete_student(self, e):
        row = e.args
        with ui.dialog() as dlg, ui.card():
            ui.label(f"Remover {row['name']}?")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dlg.close).props("flat")
                def confirm():
                    services.remove_student(row["id"])
                    dlg.close()
                    self._refresh()
                    self._audit(f"Removeu aluno: {row['name']}")
                ui.button("Remover", on_click=confirm).props("color=negative")
        dlg.open()

    def _audit(self, detail):
        try:
            username = app.storage.user.get("username", "?")
            services.log_action("aluno", detail=detail, username=username)
        except Exception:
            pass
