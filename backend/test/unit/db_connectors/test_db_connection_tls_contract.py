"""
Contrato TLS de DBConnectionConfig.

- Por defecto se verifica el certificado (tls_verify=True).
- Desactivar la verificación exige confirmar el hostname en el propio modelo, de modo que
  la regla vale para /test y /sessions aunque no se use la UI.
- tls_ca_pem solo acepta certificados PEM (nunca claves privadas) y se normaliza.
- Los campos TLS viajan en el blob cifrado (to_adapter_config) y se rehidratan.
"""

import pytest
from pydantic import ValidationError

from app.models.db_connection import DBConnectionConfig


def _config(dialect="postgresql", **extra):
    return DBConnectionConfig(
        dialect=dialect,
        host="db.example.com",
        port=5432,
        database="app",
        user="u",
        password="p",
        **extra,
    )


class TestDefaultSeguro:
    def test_verifica_por_defecto(self):
        cfg = _config()

        assert cfg.tls_verify is True
        assert cfg.tls_ca_pem is None
        assert cfg.confirm_hostname is None

    def test_to_adapter_config_incluye_tls_verify(self):
        assert _config().to_adapter_config()["tls_verify"] is True

    @pytest.mark.parametrize("valor", ["false", "no", 0, "0", None])
    def test_tls_verify_solo_acepta_booleanos(self, valor):
        """Un valor ambiguo no puede desactivar la verificación por coerción."""
        with pytest.raises(ValidationError):
            _config(tls_verify=valor, confirm_hostname="db.example.com")


class TestConfirmacionDeHostname:
    def test_opt_out_sin_confirmacion_se_rechaza(self):
        with pytest.raises(ValidationError, match="confirm_hostname"):
            _config(tls_verify=False)

    def test_opt_out_con_hostname_distinto_se_rechaza(self):
        with pytest.raises(ValidationError, match="confirm_hostname"):
            _config(tls_verify=False, confirm_hostname="otro.example.com")

    @pytest.mark.parametrize("texto", ["", "   "])
    def test_opt_out_con_confirmacion_vacia_se_rechaza(self, texto):
        with pytest.raises(ValidationError):
            _config(tls_verify=False, confirm_hostname=texto)

    @pytest.mark.parametrize(
        "texto", ["db.example.com", "DB.Example.COM", "  db.example.com  ", "db.example.com."]
    )
    def test_opt_out_con_hostname_correcto_se_acepta(self, texto):
        cfg = _config(tls_verify=False, confirm_hostname=texto)

        assert cfg.tls_verify is False

    def test_confirmar_un_prefijo_no_basta(self):
        with pytest.raises(ValidationError):
            _config(tls_verify=False, confirm_hostname="db.example")

    def test_confirmacion_irrelevante_si_se_verifica(self):
        """Con verificación activa no se exige confirmar nada."""
        assert _config(confirm_hostname="lo-que-sea").tls_verify is True

    def test_la_confirmacion_viaja_en_el_blob_cifrado(self):
        adapter_config = _config(
            tls_verify=False, confirm_hostname="db.example.com"
        ).to_adapter_config()

        assert adapter_config["tls_verify"] is False
        assert adapter_config["confirm_hostname"] == "db.example.com"

    def test_rehidratar_un_opt_out_sin_confirmacion_falla(self):
        """get_decrypted_config hace DBConnectionConfig(**blob): sin confirmación no se rehidrata."""
        blob = _config(tls_verify=False, confirm_hostname="db.example.com").to_adapter_config()
        del blob["confirm_hostname"]

        with pytest.raises(ValidationError):
            DBConnectionConfig(dialect="postgresql", **blob)

    def test_ciclo_completo_del_blob(self):
        original = _config(tls_verify=False, confirm_hostname="db.example.com")

        rehidratada = DBConnectionConfig(dialect="postgresql", **original.to_adapter_config())

        assert rehidratada.tls_verify is False


class TestCAPropia:
    def test_acepta_un_certificado_pem(self, ca_pem):
        cfg = _config(tls_ca_pem=ca_pem)

        assert "BEGIN CERTIFICATE" in cfg.tls_ca_pem
        assert cfg.to_adapter_config()["tls_ca_pem"] == cfg.tls_ca_pem

    def test_normaliza_el_pem_y_descarta_texto_ajeno(self, ca_pem):
        con_ruido = "texto previo\n" + ca_pem + "\ntexto posterior; Encrypt=no\n"

        cfg = _config(tls_ca_pem=con_ruido)

        assert "texto" not in cfg.tls_ca_pem
        assert "Encrypt" not in cfg.tls_ca_pem
        assert cfg.tls_ca_pem.startswith("-----BEGIN CERTIFICATE-----")

    def test_acepta_una_cadena_de_certificados(self, tls_certs):
        cadena = tls_certs.make_ca("CA uno")[0] + tls_certs.make_ca("CA dos")[0]

        cfg = _config(tls_ca_pem=cadena)

        assert cfg.tls_ca_pem.count("BEGIN CERTIFICATE") == 2

    def test_rechaza_mas_de_diez_certificados(self, tls_certs):
        demasiados = "".join(tls_certs.make_ca(f"CA {i}")[0] for i in range(11))

        with pytest.raises(ValidationError, match="tls_ca_pem"):
            _config(tls_ca_pem=demasiados)

    def test_rechaza_una_clave_privada(self, ca_key_pem):
        with pytest.raises(ValidationError, match="tls_ca_pem"):
            _config(tls_ca_pem=ca_key_pem)

    def test_rechaza_certificado_con_clave_privada_adjunta(self, ca_pem, ca_key_pem):
        with pytest.raises(ValidationError, match="tls_ca_pem"):
            _config(tls_ca_pem=ca_pem + ca_key_pem)

    @pytest.mark.parametrize(
        "pem", ["", "no soy un pem", "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----"]
    )
    def test_rechaza_pem_invalido(self, pem):
        with pytest.raises(ValidationError, match="tls_ca_pem"):
            _config(tls_ca_pem=pem)

    def test_rechaza_pem_demasiado_grande(self, ca_pem):
        with pytest.raises(ValidationError):
            _config(tls_ca_pem=ca_pem + "A" * 70_000)

    def test_ca_propia_es_incompatible_con_opt_out(self, ca_pem):
        with pytest.raises(ValidationError, match="tls_ca_pem"):
            _config(tls_ca_pem=ca_pem, tls_verify=False, confirm_hostname="db.example.com")

    def test_sqlserver_no_admite_ca_propia(self, ca_pem):
        with pytest.raises(ValidationError, match="SQL Server"):
            _config(dialect="sqlserver", tls_ca_pem=ca_pem)

    @pytest.mark.parametrize("dialect", ["postgresql", "mysql", "oracle"])
    def test_resto_de_dialectos_admiten_ca_propia(self, dialect, ca_pem):
        assert _config(dialect=dialect, tls_ca_pem=ca_pem).tls_ca_pem
