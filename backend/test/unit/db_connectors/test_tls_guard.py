"""
Test guardián: ningún adaptador puede volver a conectar sin verificar.

Tres capas, para que el fallo salte aunque alguien toque un adaptador o añada otro:

1. Descubrimiento: todo adaptador concreto de BaseDBAdapter debe estar en la tabla de abajo.
   Un adaptador nuevo sin cobertura TLS rompe este test.
2. Comportamiento: con la configuración por defecto (sin campos TLS), el connect() real de
   cada adaptador debe entregar al driver parámetros que verifican el certificado; con el
   opt-out, parámetros que cifran sin verificar.
3. Estático (AST): fuera de tls.py no puede aparecer ningún literal que debilite la
   verificación (sslmode débil, TrustServerCertificate=yes, CERT_NONE, ssl_disabled...).
   El propio escáner se prueba con muestras buenas y malas.
"""

import ast
import ssl
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import app.utils.db_adapters as db_adapters
from app.utils.db_adapters.base_adapter import BaseDBAdapter
from app.utils.db_adapters.mysql_adapter import MySQLAdapter
from app.utils.db_adapters.oracle_adapter import OracleAdapter
from app.utils.db_adapters.postgres_adapter import PostgreSQLAdapter
from app.utils.db_adapters.sqlserver_adapter import SQLServerAdapter

ADAPTERS_DIR = Path(db_adapters.__file__).resolve().parent
TLS_MODULE = "tls.py"


# =============================================================================
# CAPA 2 - Qué recibe el driver
# =============================================================================


def _call_text(call) -> str:
    return " ".join([*map(str, call.args), *(f"{k}={v}" for k, v in call.kwargs.items())])


# adaptador -> (módulo.función que se parchea, verifica, cifra sin verificar)
CASES = {
    PostgreSQLAdapter: (
        "app.utils.db_adapters.postgres_adapter.psycopg2.connect",
        lambda c: c.kwargs["sslmode"] == "verify-full" and "sslrootcert" in c.kwargs,
        lambda c: c.kwargs["sslmode"] == "require",
    ),
    MySQLAdapter: (
        "app.utils.db_adapters.mysql_adapter._TLSRequiredConnection",
        lambda c: (
            isinstance(c.kwargs.get("ssl"), ssl.SSLContext)
            and c.kwargs["ssl"].verify_mode == ssl.CERT_REQUIRED
            and c.kwargs["ssl"].check_hostname is True
        ),
        lambda c: (
            isinstance(c.kwargs.get("ssl"), ssl.SSLContext)
            and c.kwargs["ssl"].verify_mode == ssl.CERT_NONE
        ),
    ),
    SQLServerAdapter: (
        "app.utils.db_adapters.sqlserver_adapter.pyodbc.connect",
        lambda c: "Encrypt=yes;" in c.args[0] and "TrustServerCertificate=no;" in c.args[0],
        lambda c: "Encrypt=yes;" in c.args[0] and "TrustServerCertificate=yes;" in c.args[0],
    ),
    OracleAdapter: (
        "app.utils.db_adapters.oracle_adapter.oracledb.connect",
        lambda c: (
            c.kwargs["protocol"] == "tcps"
            and c.kwargs["ssl_server_dn_match"] is True
            and c.kwargs["ssl_context"].verify_mode == ssl.CERT_REQUIRED
        ),
        lambda c: (
            c.kwargs["protocol"] == "tcps"
            and c.kwargs["ssl_server_dn_match"] is False
            and c.kwargs["ssl_context"].verify_mode == ssl.CERT_NONE
        ),
    ),
}


def _concrete_adapters():
    pending, found = list(BaseDBAdapter.__subclasses__()), set()
    while pending:
        cls = pending.pop()
        pending.extend(cls.__subclasses__())
        if cls.__module__.startswith("app.utils.db_adapters") and not getattr(
            cls, "__abstractmethods__", None
        ):
            found.add(cls)
    return found


def _config(**extra):
    return {
        "host": "db.example.com",
        "port": 1234,
        "database": "app",
        "user": "u",
        "password": "p",
        **extra,
    }


def _connect(adapter_cls, **extra):
    patch_target = CASES[adapter_cls][0]
    with patch(patch_target) as mock_connect:
        mock_connect.return_value = MagicMock()
        adapter_cls(_config(**extra)).connect()
    return mock_connect.call_args


class TestTodoAdaptadorTieneCoberturaTLS:
    def test_la_tabla_cubre_exactamente_los_adaptadores_existentes(self):
        assert _concrete_adapters() == set(CASES), (
            "Hay un adaptador sin caso TLS en test_tls_guard.CASES (o uno obsoleto): "
            "añádelo con lo que debe recibir su driver al verificar y al hacer opt-out"
        )

    @pytest.mark.parametrize("adapter_cls", sorted(CASES, key=lambda c: c.__name__))
    def test_connect_usa_la_politica_tls(self, adapter_cls):
        """connect() debe consultar self.tls (directa o indirectamente)."""
        source = ADAPTERS_DIR / f"{adapter_cls.__module__.rsplit('.', 1)[1]}.py"

        assert "self.tls" in source.read_text(encoding="utf-8")


class TestPorDefectoSeVerifica:
    @pytest.mark.parametrize("adapter_cls", sorted(CASES, key=lambda c: c.__name__))
    def test_sin_campos_tls_el_driver_recibe_parametros_que_verifican(self, adapter_cls):
        call = _connect(adapter_cls)

        assert CASES[adapter_cls][1](call), (
            f"{adapter_cls.__name__} conecta sin verificar certificado y hostname por defecto: "
            f"{_call_text(call)}"
        )

    @pytest.mark.parametrize("adapter_cls", sorted(CASES, key=lambda c: c.__name__))
    def test_tls_verify_true_explicito_es_lo_mismo(self, adapter_cls):
        assert CASES[adapter_cls][1](_connect(adapter_cls, tls_verify=True))


class TestOptOutSigueCifrando:
    @pytest.mark.parametrize("adapter_cls", sorted(CASES, key=lambda c: c.__name__))
    def test_el_opt_out_cifra_pero_no_verifica(self, adapter_cls):
        call = _connect(adapter_cls, tls_verify=False, confirm_hostname="db.example.com")

        assert CASES[adapter_cls][2](call), (
            f"{adapter_cls.__name__}: con tls_verify=false debe seguir cifrando: "
            f"{_call_text(call)}"
        )

    @pytest.mark.parametrize("adapter_cls", sorted(CASES, key=lambda c: c.__name__))
    def test_el_opt_out_no_se_activa_sin_confirmar_el_hostname(self, adapter_cls):
        from app.utils.db_adapters.exceptions import DBValidationError

        with pytest.raises(DBValidationError):
            adapter_cls(_config(tls_verify=False))


# =============================================================================
# CAPA 3 - Escáner estático
# =============================================================================

# sslmode que sí se admiten fuera de tls.py
SSLMODE_PERMITIDOS = {"verify-full", "require"}


def _violations(source: str, filename: str = "<muestra>"):
    """Construcciones que debilitan la verificación TLS en el código fuente dado."""
    found = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.lower().replace(" ", "")
            for fragment in (
                "trustservercertificate=yes",
                "encrypt=no",
                "encrypt=optional",
                "sslmode=disable",
                "sslmode=allow",
                "sslmode=prefer",
                "protocol=tcp)",
            ):
                if fragment in text:
                    found.append(f"{filename}:{line} literal '{fragment}'")

        if isinstance(node, ast.Attribute) and node.attr in {
            "CERT_NONE",
            "CERT_OPTIONAL",
            "_create_unverified_context",
        }:
            found.append(f"{filename}:{line} {node.attr}")

        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                value = keyword.value
                is_false = isinstance(value, ast.Constant) and value.value is False
                if keyword.arg == "sslmode" and not (
                    isinstance(value, ast.Constant) and value.value in SSLMODE_PERMITIDOS
                ):
                    # sslmode dinámico o débil: solo se admiten los literales permitidos
                    found.append(f"{filename}:{line} sslmode no permitido")
                if keyword.arg in {"ssl_verify_cert", "ssl_verify_identity"} and is_false:
                    found.append(f"{filename}:{line} {keyword.arg}=False")
                if keyword.arg == "ssl_disabled" and not is_false:
                    found.append(f"{filename}:{line} ssl_disabled")
                if keyword.arg == "ssl_server_dn_match" and is_false:
                    found.append(f"{filename}:{line} ssl_server_dn_match=False")
                if keyword.arg == "verify" and is_false:
                    found.append(f"{filename}:{line} verify=False")
                if keyword.arg == "protocol" and isinstance(value, ast.Constant):
                    if str(value.value).lower() == "tcp":
                        found.append(f"{filename}:{line} protocol=tcp")
                if keyword.arg == "check_hostname" and is_false:
                    found.append(f"{filename}:{line} check_hostname=False")

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "check_hostname":
                    if isinstance(node.value, ast.Constant) and node.value.value is False:
                        found.append(f"{filename}:{line} check_hostname = False")
    return found


class TestEscanerEstatico:
    @pytest.mark.parametrize(
        "source",
        [
            'cs = "DRIVER={x};TrustServerCertificate=yes;"',
            'cs = "Encrypt=no;"',
            'cs = "Encrypt=optional;"',
            'psycopg2.connect(sslmode="prefer")',
            'psycopg2.connect(sslmode="disable")',
            "psycopg2.connect(sslmode=mode)",
            "pymysql.connect(ssl_disabled=True)",
            "pymysql.connect(ssl_verify_cert=False)",
            "pymysql.connect(ssl_verify_identity=False)",
            "ctx.verify_mode = ssl.CERT_NONE",
            "ssl._create_unverified_context()",
            "ctx.check_hostname = False",
            "oracledb.connect(ssl_server_dn_match=False)",
            'oracledb.connect(protocol="tcp")',
            "requests.get(url, verify=False)",
        ],
    )
    def test_detecta_construcciones_inseguras(self, source):
        assert _violations(source), f"El escáner no detecta: {source}"

    @pytest.mark.parametrize(
        "source",
        [
            'psycopg2.connect(sslmode="verify-full", sslrootcert=path)',
            'psycopg2.connect(sslmode="require")',
            'cs = "Encrypt=yes;TrustServerCertificate=no;"',
            "cs = f'Encrypt=yes;TrustServerCertificate={value};'",
            "pymysql.connect(ssl=build_ssl_context(options))",
            'oracledb.connect(protocol="tcps", ssl_server_dn_match=options.verify)',
            "ctx.check_hostname = True",
        ],
    )
    def test_no_marca_construcciones_seguras(self, source):
        assert _violations(source) == []

    def test_los_adaptadores_no_debilitan_la_verificacion_fuera_de_tls_py(self):
        violations = []
        for path in sorted(ADAPTERS_DIR.glob("*.py")):
            if path.name == TLS_MODULE:
                continue
            violations += _violations(path.read_text(encoding="utf-8"), path.name)

        assert (
            not violations
        ), "Solo tls.py puede desactivar la verificación TLS. Hallado: " + "; ".join(violations)

    def test_tls_py_es_el_unico_sitio_con_cert_none(self):
        con_cert_none = [
            path.name
            for path in sorted(ADAPTERS_DIR.glob("*.py"))
            if "CERT_NONE" in path.read_text(encoding="utf-8")
        ]

        assert con_cert_none == [TLS_MODULE]
