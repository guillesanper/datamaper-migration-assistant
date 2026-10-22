"""
Unit tests for app.models.db_connection.DBConnectionConfig

Tests del contrato de configuración de conexión:
- Los campos específicos de Oracle (service_name, sid) llegan al adaptador
"""

import pytest

from app.models.db_connection import DBConnectionConfig


def _oracle_config(**extra):
    return DBConnectionConfig(
        dialect="oracle",
        host="db.example.com",
        port=1521,
        database="ORCL",
        user="scott",
        password="tiger",
        **extra,
    )


class TestOracleIdentifiers:
    """service_name y sid no deben perderse entre la API y el adaptador."""

    def test_service_name_llega_al_adaptador(self):
        cfg = _oracle_config(service_name="SALES")

        assert cfg.to_adapter_config()["service_name"] == "SALES"

    def test_sid_llega_al_adaptador(self):
        cfg = _oracle_config(sid="XE")

        assert cfg.to_adapter_config()["sid"] == "XE"

    def test_sin_service_name_ni_sid_no_se_emiten_claves_vacias(self):
        adapter_config = _oracle_config().to_adapter_config()

        assert "service_name" not in adapter_config
        assert "sid" not in adapter_config

    def test_service_name_sobrevive_al_ciclo_de_cifrado(self):
        """El blob cifrado se rehidrata con DBConnectionConfig(**blob)."""
        original = _oracle_config(service_name="SALES")

        rehidratada = DBConnectionConfig(dialect="oracle", **original.to_adapter_config())

        assert rehidratada.service_name == "SALES"

    @pytest.mark.parametrize("dialect", ["postgresql", "mysql", "sqlserver"])
    def test_otros_dialectos_no_emiten_identificadores_oracle(self, dialect):
        cfg = DBConnectionConfig(
            dialect=dialect,
            host="db.example.com",
            port=5432,
            database="app",
            user="u",
            password="p",
        )

        adapter_config = cfg.to_adapter_config()

        assert "service_name" not in adapter_config
        assert "sid" not in adapter_config
