import services


class TestAuditLog:
    def test_log_and_list(self):
        services.log_action("livro", detail="Livro adicionado", username="admin")
        rows = services.list_audit()
        assert len(rows) == 1
        assert rows[0]["action"] == "livro"
        assert rows[0]["detail"] == "Livro adicionado"
        assert rows[0]["username"] == "admin"
        assert rows[0]["ts"]  # timestamp preenchido

    def test_default_username_is_system(self):
        services.log_action("job", detail="backup")
        assert services.list_audit()[0]["username"] == "system"

    def test_list_ordered_newest_first(self):
        services.log_action("a", detail="1", username="u")
        services.log_action("b", detail="2", username="u")
        services.log_action("c", detail="3", username="u")
        actions = [r["action"] for r in services.list_audit()]
        assert actions == ["c", "b", "a"]

    def test_limit(self):
        for i in range(5):
            services.log_action("x", detail=str(i), username="u")
        assert len(services.list_audit(limit=2)) == 2

    def test_empty(self):
        assert services.list_audit() == []
