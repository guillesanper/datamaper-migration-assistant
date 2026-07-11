"""
Unit tests for _are_types_mapping_compatible() and _TYPE_COMPATIBILITY
in app.routers.mappings.

TypeMapper.extract_type_name() is already tested in
test/unit/db_connectors/test_type_mappers.py — not repeated here.
"""
import pytest

from app.routers.mappings import _TYPE_COMPATIBILITY, _are_types_mapping_compatible


class TestAreTypesMappingCompatible:

    # ------------------------------------------------------------------
    # Same-type mappings (primary bug fix — UUID→UUID must pass)
    # ------------------------------------------------------------------

    def test_uuid_to_uuid(self):
        assert _are_types_mapping_compatible("UUID", "UUID") is True

    def test_integer_to_integer(self):
        assert _are_types_mapping_compatible("INTEGER", "INTEGER") is True

    def test_timestamp_to_timestamp(self):
        assert _are_types_mapping_compatible("TIMESTAMP", "TIMESTAMP") is True

    def test_json_to_json(self):
        assert _are_types_mapping_compatible("JSON", "JSON") is True

    def test_boolean_to_boolean(self):
        assert _are_types_mapping_compatible("BOOLEAN", "BOOLEAN") is True

    # ------------------------------------------------------------------
    # Cross-family allowed
    # ------------------------------------------------------------------

    def test_integer_to_text(self):
        assert _are_types_mapping_compatible("INTEGER", "TEXT") is True

    def test_integer_to_bigint(self):
        assert _are_types_mapping_compatible("INTEGER", "BIGINT") is True

    def test_date_to_timestamp(self):
        assert _are_types_mapping_compatible("DATE", "TIMESTAMP") is True

    def test_json_to_jsonb(self):
        assert _are_types_mapping_compatible("JSON", "JSONB") is True

    def test_uuid_to_varchar(self):
        assert _are_types_mapping_compatible("UUID", "VARCHAR") is True

    def test_boolean_to_integer(self):
        assert _are_types_mapping_compatible("BOOLEAN", "INTEGER") is True

    def test_decimal_to_numeric(self):
        assert _are_types_mapping_compatible("DECIMAL", "NUMERIC") is True

    # ------------------------------------------------------------------
    # Cross-family rejected
    # ------------------------------------------------------------------

    def test_uuid_to_integer_rejected(self):
        assert _are_types_mapping_compatible("UUID", "INTEGER") is False

    def test_uuid_to_date_rejected(self):
        assert _are_types_mapping_compatible("UUID", "DATE") is False

    def test_text_to_integer_rejected(self):
        assert _are_types_mapping_compatible("TEXT", "INTEGER") is False

    def test_json_to_integer_rejected(self):
        assert _are_types_mapping_compatible("JSON", "INTEGER") is False

    def test_date_to_integer_rejected(self):
        assert _are_types_mapping_compatible("DATE", "INTEGER") is False

    def test_boolean_to_date_rejected(self):
        assert _are_types_mapping_compatible("BOOLEAN", "DATE") is False

    # ------------------------------------------------------------------
    # Parameterised inputs — normalisation via TypeMapper.extract_type_name
    # ------------------------------------------------------------------

    def test_varchar_255_to_text(self):
        assert _are_types_mapping_compatible("VARCHAR(255)", "TEXT") is True

    def test_decimal_precision_to_numeric(self):
        assert _are_types_mapping_compatible("DECIMAL(10,2)", "NUMERIC") is True

    def test_varchar_different_lengths(self):
        assert _are_types_mapping_compatible("VARCHAR(255)", "VARCHAR(100)") is True

    def test_numeric_parameterised_same_type(self):
        assert _are_types_mapping_compatible("NUMERIC(10,2)", "NUMERIC(5,0)") is True

    # ------------------------------------------------------------------
    # Case-insensitive inputs
    # ------------------------------------------------------------------

    def test_lowercase_uuid_to_uuid(self):
        assert _are_types_mapping_compatible("uuid", "uuid") is True

    def test_mixed_case_varchar_to_text(self):
        assert _are_types_mapping_compatible("Varchar(255)", "text") is True

    def test_lowercase_integer_to_text(self):
        assert _are_types_mapping_compatible("integer", "TEXT") is True

    # ------------------------------------------------------------------
    # Unknown / unrecognised types — fail closed
    # ------------------------------------------------------------------

    def test_unknown_origin_rejected(self):
        assert _are_types_mapping_compatible("CUSTOM_TYPE", "TEXT") is False

    def test_unknown_dest_rejected(self):
        assert _are_types_mapping_compatible("INTEGER", "CUSTOM_TYPE") is False

    def test_both_unknown_rejected(self):
        assert _are_types_mapping_compatible("CUSTOM_A", "CUSTOM_B") is False


class TestTypeCompatibilityMatrix:
    """Structural invariants — catch maintenance mistakes early."""

    def test_all_keys_uppercase(self):
        for k in _TYPE_COMPATIBILITY:
            assert k == k.upper(), f"Key {k!r} is not uppercase"

    def test_all_values_uppercase(self):
        for k, vs in _TYPE_COMPATIBILITY.items():
            for v in vs:
                assert v == v.upper(), f"Value {v!r} under key {k!r} is not uppercase"

    def test_every_type_maps_to_itself(self):
        """Every type must be reflexive — can always map to its own kind."""
        for type_name in _TYPE_COMPATIBILITY:
            assert type_name in _TYPE_COMPATIBILITY[type_name], (
                f"{type_name!r} is not reflexive in _TYPE_COMPATIBILITY"
            )
