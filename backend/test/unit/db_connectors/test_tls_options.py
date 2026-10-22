"""
Tests de app.utils.db_adapters.tls: la decisión de cómo se verifica vive en un único sitio.

- TLSOptions.from_config falla cerrado: ante cualquier duda se verifica o se rechaza.
- trust_file entrega la CA a los drivers que exigen una ruta y la borra siempre.
- build_ssl_context construye el contexto para los drivers que lo aceptan (oracledb).
"""

import os
import ssl
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils.db_adapters.exceptions import DBValidationError
from app.utils.db_adapters.postgres_adapter import PostgreSQLAdapter
from app.utils.db_adapters.tls import TLSOptions, build_ssl_context, default_ca_bundle, trust_file


def _config(**extra):
    config = {
        "host": "db.example.com",
        "port": 5432,
        "database": "app",
        "user": "u",
        "password": "p",
    }
    config.update(extra)
    return config


class TestFromConfig:
    def test_sin_campos_tls_se_verifica(self):
        options = TLSOptions.from_config(_config())

        assert options.verify is True
        assert options.ca_pem is None

    def test_opt_out_con_confirmacion_correcta(self):
        options = TLSOptions.from_config(
            _config(tls_verify=False, confirm_hostname="DB.example.com.")
        )

        assert options.verify is False

    @pytest.mark.parametrize("confirm", [None, "", "otro.example.com"])
    def test_opt_out_sin_confirmacion_valida_se_rechaza(self, confirm):
        """Defensa en profundidad: el adaptador se puede construir sin pasar por el modelo."""
        with pytest.raises(DBValidationError, match="confirm_hostname"):
            TLSOptions.from_config(_config(tls_verify=False, confirm_hostname=confirm))

    @pytest.mark.parametrize("valor", ["false", 0, "no", None])
    def test_tls_verify_no_booleano_se_rechaza(self, valor):
        with pytest.raises(DBValidationError, match="tls_verify"):
            TLSOptions.from_config(_config(tls_verify=valor))

    def test_ca_propia_con_opt_out_se_rechaza(self, ca_pem):
        with pytest.raises(DBValidationError, match="tls_ca_pem"):
            TLSOptions.from_config(
                _config(tls_verify=False, confirm_hostname="db.example.com", tls_ca_pem=ca_pem)
            )

    @pytest.mark.parametrize("valor", [123, b"bytes", ["lista"]])
    def test_ca_que_no_es_texto_se_rechaza(self, valor):
        with pytest.raises(DBValidationError, match="tls_ca_pem"):
            TLSOptions.from_config(_config(tls_ca_pem=valor))

    def test_ca_con_clave_privada_se_rechaza(self, ca_key_pem):
        with pytest.raises(DBValidationError, match="tls_ca_pem"):
            TLSOptions.from_config(_config(tls_ca_pem=ca_key_pem))

    def test_ca_valida_se_conserva(self, ca_pem):
        assert TLSOptions.from_config(_config(tls_ca_pem=ca_pem)).ca_pem == ca_pem

    def test_es_inmutable(self):
        options = TLSOptions.from_config(_config())

        with pytest.raises(AttributeError):
            options.verify = False  # type: ignore[misc]


class TestTrustFile:
    def test_sin_ca_propia_entrega_el_bundle_del_sistema_y_no_lo_borra(self):
        with trust_file(None) as path:
            assert Path(path).is_file()
            assert path == default_ca_bundle()

        assert Path(default_ca_bundle()).is_file()

    def test_con_ca_propia_escribe_y_borra(self, ca_pem):
        with trust_file(ca_pem) as path:
            assert Path(path).read_text() == ca_pem
            assert path != default_ca_bundle()

        assert not Path(path).exists()

    def test_se_borra_aunque_falle_el_bloque(self, ca_pem):
        with pytest.raises(RuntimeError):
            with trust_file(ca_pem) as path:
                raise RuntimeError("fallo del driver")

        assert not Path(path).exists()

    def test_se_borra_si_falla_la_escritura(self, ca_pem):
        creados = []
        real_mkstemp = __import__("tempfile").mkstemp

        def espiar(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            creados.append(path)
            return fd, path

        with (
            patch("app.utils.db_adapters.tls.tempfile.mkstemp", side_effect=espiar),
            patch("app.utils.db_adapters.tls.os.write", side_effect=OSError("disco lleno")),
        ):
            with pytest.raises(OSError):
                with trust_file(ca_pem):
                    pass

        assert creados and not Path(creados[0]).exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="los permisos POSIX no aplican en Windows")
    def test_el_archivo_es_privado(self, ca_pem):
        with trust_file(ca_pem) as path:
            assert os.stat(path).st_mode & 0o777 == 0o600

    def test_cada_uso_crea_un_archivo_distinto(self, ca_pem):
        with trust_file(ca_pem) as primero, trust_file(ca_pem) as segundo:
            assert primero != segundo


class TestSSLContext:
    def test_verificando_exige_certificado_y_hostname(self):
        context = build_ssl_context(TLSOptions(verify=True))

        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True

    def test_verificando_sin_ca_propia_confia_en_el_bundle_del_sistema(self):
        assert build_ssl_context(TLSOptions(verify=True)).get_ca_certs()

    def test_con_ca_propia_solo_confia_en_ella(self, ca_pem):
        context = build_ssl_context(TLSOptions(verify=True, ca_pem=ca_pem))

        certificados = context.get_ca_certs()
        assert len(certificados) == 1
        assert ("commonName", "Datamap Test CA") in [
            atributo for rdn in certificados[0]["subject"] for atributo in rdn
        ]

    def test_opt_out_cifra_pero_no_verifica(self):
        context = build_ssl_context(TLSOptions(verify=False))

        assert context.verify_mode == ssl.CERT_NONE
        assert context.check_hostname is False

    @pytest.mark.parametrize("verify", [True, False])
    def test_nunca_admite_versiones_antiguas_de_tls(self, verify):
        context = build_ssl_context(TLSOptions(verify=verify))

        assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


class TestBaseAdapter:
    def test_el_adaptador_expone_el_estado_tls(self):
        adapter = PostgreSQLAdapter(_config())

        assert adapter.tls.verify is True
        assert adapter.connection_info["tls_verified"] is True

    def test_el_adaptador_sin_verificar_lo_refleja(self):
        adapter = PostgreSQLAdapter(_config(tls_verify=False, confirm_hostname="db.example.com"))

        assert adapter.connection_info["tls_verified"] is False

    def test_el_adaptador_rechaza_opt_out_sin_confirmacion(self):
        with pytest.raises(DBValidationError, match="confirm_hostname"):
            PostgreSQLAdapter(_config(tls_verify=False))

    def test_connection_info_no_expone_la_ca_ni_la_confirmacion(self, ca_pem):
        info = PostgreSQLAdapter(_config(tls_ca_pem=ca_pem)).connection_info

        assert "tls_ca_pem" not in info
        assert "confirm_hostname" not in info
