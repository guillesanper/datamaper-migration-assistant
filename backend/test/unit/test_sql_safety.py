"""
Unit Tests for SQL safety helpers (quoting, validación y split de scripts)
"""

import pytest

from app.utils.sql_safety import (
    UnsafeSQLError,
    is_transaction_control,
    quote_identifier,
    quote_literal,
    sanitize_comment,
    split_sql_statements,
    validate_sql_expression,
    validate_sql_type,
)


class TestQuoteIdentifier:
    def test_simple_identifiers_unchanged(self):
        assert quote_identifier("customers") == "customers"
        assert quote_identifier("public.orders") == "public.orders"

    def test_special_names_quoted_per_dialect(self):
        assert quote_identifier("order-items", "postgresql") == '"order-items"'
        assert quote_identifier("order-items", "mysql") == "`order-items`"
        assert quote_identifier("order-items", "sqlserver") == "[order-items]"
        assert quote_identifier("Año", "oracle") == '"Año"'

    def test_closing_quote_is_escaped(self):
        assert quote_identifier('x"; DROP TABLE t; --') == '"x""; DROP TABLE t; --"'
        assert quote_identifier("x`y", "mysql") == "`x``y`"
        assert quote_identifier("x]y", "sqlserver") == "[x]]y]"

    def test_rejects_empty_and_control_chars(self):
        for bad in ("", "  ", "a..b", "a\nDROP TABLE t"):
            with pytest.raises(UnsafeSQLError):
                quote_identifier(bad)


class TestQuoteLiteral:
    def test_escapes_single_quotes(self):
        assert quote_literal("o'brien") == "'o''brien'"

    def test_mysql_escapes_backslash(self):
        assert quote_literal("a\\", "mysql") == "'a\\\\'"


class TestValidateSqlType:
    @pytest.mark.parametrize(
        "type_name",
        ["INTEGER", "VARCHAR(255)", "DECIMAL(10, 2)", "DOUBLE PRECISION", "TEXT[]"],
    )
    def test_valid_types(self, type_name):
        assert validate_sql_type(type_name) == type_name

    @pytest.mark.parametrize(
        "type_name", ["INT); DROP TABLE t; --", "VARCHAR(10) || 'x'", "INT -- c", ""]
    )
    def test_invalid_types(self, type_name):
        with pytest.raises(UnsafeSQLError):
            validate_sql_type(type_name)


class TestValidateSqlExpression:
    @pytest.mark.parametrize(
        "expr",
        [
            "UPPER(TRIM({column}))",
            "COALESCE({column}, 'a;b -- not a comment')",
            "CASE WHEN {column} = 'it''s' THEN 1 ELSE 0 END",
        ],
    )
    def test_valid_expressions(self, expr):
        assert validate_sql_expression(expr) == expr

    @pytest.mark.parametrize(
        "expr",
        [
            "{column}); DROP TABLE users; --",
            "{column} -- comment",
            "{column} /* c */",
            "UPPER({column}",
            "{column})",
            "'unterminated",
            "$$ evil $$",
        ],
    )
    def test_rejects_statement_breaking_expressions(self, expr):
        with pytest.raises(UnsafeSQLError):
            validate_sql_expression(expr)


def test_sanitize_comment_removes_newlines():
    assert "\n" not in sanitize_comment("P\nDROP TABLE victims;")


class TestSplitSqlStatements:
    def test_respects_literals_and_comments(self):
        script = """
        -- header; with semicolon
        INSERT INTO t (a) SELECT 'x;y -- z' FROM s; /* c; */
        COMMIT;
        """
        assert split_sql_statements(script) == [
            "INSERT INTO t (a) SELECT 'x;y -- z' FROM s",
            "COMMIT",
        ]

    def test_quoted_identifier_with_semicolon_stays_in_one_statement(self):
        stmt = 'INSERT INTO "x""; DROP TABLE t; --" (a) SELECT a FROM s'
        assert split_sql_statements(stmt + ";") == [stmt]

    def test_postgres_dollar_quoted_block(self):
        script = "DO $$\nBEGIN\n  INSERT INTO t VALUES (1);\nEND $$;\nSELECT 1;"
        statements = split_sql_statements(script, "postgresql")
        assert len(statements) == 2
        assert statements[0].startswith("DO $$") and statements[0].endswith("END $$")

    def test_oracle_plsql_block(self):
        script = (
            "SET TRANSACTION READ WRITE;\n"
            "DECLARE\n  x NUMBER := 1;\nBEGIN\n  INSERT INTO t VALUES (x);\nEND;\n/\n"
            "COMMIT;"
        )
        statements = split_sql_statements(script, "oracle")
        assert statements[0] == "SET TRANSACTION READ WRITE"
        assert statements[1].startswith("DECLARE") and statements[1].rstrip().endswith("END;")
        assert statements[2] == "COMMIT"


@pytest.mark.parametrize(
    "stmt",
    [
        "BEGIN",
        "begin;",
        "START TRANSACTION",
        "BEGIN TRANSACTION",
        "COMMIT",
        "COMMIT TRANSACTION",
        "ROLLBACK",
        "SET AUTOCOMMIT=0",
        "SET TRANSACTION READ WRITE",
    ],
)
def test_transaction_control_detected(stmt):
    assert is_transaction_control(stmt)


@pytest.mark.parametrize(
    "stmt", ["INSERT INTO commits (id) VALUES (1)", "DO $$ BEGIN NULL; END $$", "SELECT 1"]
)
def test_regular_statements_not_transaction_control(stmt):
    assert not is_transaction_control(stmt)
