from app.models.database import Base


class TestDatabaseModels:
    def test_all_tables_present(self):
        tables = Base.metadata.tables
        expected = [
            "clientes",
            "conversaciones",
            "mensajes",
            "citas",
            "servicios",
            "quejas",
            "perfiles_usuario",
            "recordatorios",
            "logs",
            "metricas",
        ]
        for table in expected:
            assert table in tables, f"Falta tabla: {table}"
        assert len(tables) == 11

    def test_tables_have_columns(self):
        tables = Base.metadata.tables
        for name, table in tables.items():
            assert len(table.columns) > 0, f"Tabla {name} sin columnas"

    def test_clientes_columns(self):
        cols = Base.metadata.tables["clientes"].columns
        assert "nombre" in cols
        assert "telefono" in cols
        assert "motos_registradas" in cols

    def test_mensajes_has_fulltext(self):
        table = Base.metadata.tables["mensajes"]
        indexes = [idx for idx in table.indexes]
        fulltext = [i for i in indexes if i.dialect_kwargs.get("mysql_prefix") == "FULLTEXT"]
        assert len(fulltext) >= 1

    def test_recordatorios_has_pendientes_index(self):
        table = Base.metadata.tables["recordatorios"]
        assert any("pendientes" in str(idx) for idx in table.indexes)
