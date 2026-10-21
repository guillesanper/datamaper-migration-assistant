"""
SQL Safety Helpers

Utilidades para construir scripts SQL de migración de forma segura:
- Quoting de identificadores por dialecto (solo cuando hace falta)
- Escapado de literales
- Validación de tipos de datos y expresiones de transformación
- División de scripts en sentencias respetando comillas, comentarios y bloques
- Detección de sentencias de control de transacciones

Los nombres de tablas/columnas, tipos y transformaciones provienen de mappings
editables por los miembros del proyecto, por lo que NUNCA deben interpolarse
directamente en SQL sin pasar por estas funciones.
"""

import re
from typing import List, Optional

# Identificador "simple": se deja sin comillas para preservar la semántica de
# case-folding del motor (p.ej. PostgreSQL pasa a minúsculas los no citados).
_SIMPLE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Tipo de dato: nombre (posiblemente multi-palabra) con precisión/escala opcional.
# Ej: INTEGER, VARCHAR(255), DECIMAL(10, 2), DOUBLE PRECISION, TIMESTAMP WITH TIME ZONE
_SQL_TYPE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*)*"
    r"(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?(?:\s*\[\s*\])?$"
)

_TRANSACTION_CONTROL = re.compile(
    r"^(?:"
    r"BEGIN(?:\s+(?:TRANSACTION|TRAN|WORK))?"
    r"|START\s+TRANSACTION.*"
    r"|COMMIT(?:\s+(?:TRANSACTION|TRAN|WORK))?"
    r"|END(?:\s+(?:TRANSACTION|WORK))?"
    r"|ROLLBACK.*"
    r"|SAVEPOINT\s+.*"
    r"|RELEASE(?:\s+SAVEPOINT)?\s+.*"
    r"|SET\s+TRANSACTION\s+.*"
    r"|SET\s+AUTOCOMMIT\s*=.*"
    r"|SET\s+IMPLICIT_TRANSACTIONS\s+.*"
    r")$",
    re.IGNORECASE | re.DOTALL,
)

# Sin "^": se usa con pattern.match(text, pos), que ya ancla en pos
_PLSQL_BLOCK_START = re.compile(r"\s*(DECLARE|BEGIN)\b", re.IGNORECASE)
_PLSQL_BLOCK_END = re.compile(r"^[ \t]*/[ \t]*$", re.MULTILINE)
_DOLLAR_TAG = re.compile(r"\$[A-Za-z_]*\$")


class UnsafeSQLError(ValueError):
    """Un valor no puede incluirse de forma segura en un script SQL"""

    pass


def _check_no_control_chars(value: str, what: str) -> None:
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise UnsafeSQLError(f"{what} contains control characters: {value!r}")


def quote_identifier(name: str, dialect: str = "postgresql") -> str:
    """
    Cita un identificador (posiblemente cualificado: schema.tabla) para el dialecto.

    Las partes que son identificadores simples se dejan sin citar; el resto se
    citan escapando el carácter de cierre, de modo que nunca puedan romper la
    sentencia.

    Raises:
        UnsafeSQLError: Si el nombre está vacío o contiene caracteres de control
    """
    if name is None or not str(name).strip():
        raise UnsafeSQLError("Identifier cannot be empty")

    name = str(name).strip()
    _check_no_control_chars(name, "Identifier")

    parts = name.split(".")
    if any(not part for part in parts):
        raise UnsafeSQLError(f"Invalid qualified identifier: {name!r}")

    return ".".join(_quote_part(part, dialect) for part in parts)


def _quote_part(part: str, dialect: str) -> str:
    if _SIMPLE_IDENTIFIER.match(part):
        return part

    dialect = (dialect or "").lower()
    if dialect == "mysql":
        return "`" + part.replace("`", "``") + "`"
    if dialect == "sqlserver":
        return "[" + part.replace("]", "]]") + "]"
    # postgresql, oracle y estándar SQL
    return '"' + part.replace('"', '""') + '"'


def quote_literal(value: str, dialect: str = "postgresql") -> str:
    """Devuelve un literal de string SQL escapado para el dialecto."""
    value = str(value)
    _check_no_control_chars(value, "Literal")
    escaped = value.replace("'", "''")
    if (dialect or "").lower() == "mysql":
        # MySQL interpreta '\' como escape en literales (modo por defecto)
        escaped = escaped.replace("\\", "\\\\")
    return "'" + escaped + "'"


def safe_routine_suffix(name: str) -> str:
    """Convierte un nombre arbitrario en un sufijo válido para nombres de rutinas."""
    suffix = re.sub(r"[^A-Za-z0-9_]", "_", str(name))
    return suffix[:48] or "table"


def validate_sql_type(type_name: str) -> str:
    """
    Valida un nombre de tipo de dato antes de usarlo en CAST(... AS tipo).

    Raises:
        UnsafeSQLError: Si no tiene forma de tipo SQL
    """
    type_name = str(type_name).strip()
    if not _SQL_TYPE.match(type_name):
        raise UnsafeSQLError(f"Invalid SQL data type: {type_name!r}")
    return type_name


def sanitize_comment(text: Optional[str], max_length: int = 200) -> str:
    """Prepara texto libre para un comentario de línea (`-- ...`)."""
    if not text:
        return ""
    cleaned = "".join(ch if ord(ch) >= 32 and ord(ch) != 127 else " " for ch in str(text))
    return cleaned[:max_length]


def validate_sql_expression(expression: str) -> str:
    """
    Valida una expresión de transformación custom (ej: "UPPER(TRIM({column}))").

    Las transformaciones son expresiones SQL por diseño, así que no pueden citarse;
    se exige que sean UNA expresión: sin terminadores de sentencia ni comentarios
    fuera de literales, con comillas y paréntesis balanceados.

    Raises:
        UnsafeSQLError: Si la expresión podría romper la sentencia que la contiene
    """
    expression = str(expression)
    _check_no_control_chars(expression.replace("\n", " ").replace("\t", " "), "Expression")

    depth = 0
    i = 0
    n = len(expression)
    while i < n:
        ch = expression[i]
        if ch in ("'", '"', "`"):
            end = _find_closing_quote(expression, i, ch)
            if end < 0:
                raise UnsafeSQLError("Transformation has an unterminated quoted string")
            i = end + 1
            continue
        if ch == ";":
            raise UnsafeSQLError("Transformation cannot contain ';'")
        if expression.startswith("--", i) or expression.startswith("/*", i):
            raise UnsafeSQLError("Transformation cannot contain SQL comments")
        if expression.startswith("*/", i):
            raise UnsafeSQLError("Transformation cannot contain SQL comments")
        if ch == "$" and _DOLLAR_TAG.match(expression, i):
            raise UnsafeSQLError("Transformation cannot contain dollar-quoted blocks")
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise UnsafeSQLError("Transformation has unbalanced parentheses")
        i += 1

    if depth != 0:
        raise UnsafeSQLError("Transformation has unbalanced parentheses")

    return expression


def _find_closing_quote(text: str, start: int, quote: str) -> int:
    """Devuelve el índice de la comilla de cierre (las dobladas son escapes) o -1."""
    i = start + 1
    n = len(text)
    while i < n:
        if text[i] == quote:
            if i + 1 < n and text[i + 1] == quote:
                i += 2
                continue
            return i
        i += 1
    return -1


def split_sql_statements(script: str, dialect: str = "postgresql") -> List[str]:
    """
    Divide un script en sentencias individuales.

    A diferencia de un split por ';', respeta:
    - Literales '...' y identificadores "..." / `...` / [...] (SQL Server)
    - Comentarios -- y /* */ (se eliminan)
    - Bloques dollar-quoted de PostgreSQL ($$ ... $$, $tag$ ... $tag$)
    - Bloques PL/SQL de Oracle (DECLARE/BEGIN ... terminados por una línea "/")

    Returns:
        Lista de sentencias sin ';' final ni comentarios
    """
    dialect = (dialect or "").lower()
    statements: List[str] = []
    current: List[str] = []
    i = 0
    n = len(script)

    def flush() -> None:
        stmt = "".join(current).strip()
        if stmt:
            statements.append(stmt)
        current.clear()

    while i < n:
        # Bloques PL/SQL: consumir hasta una línea que solo contenga "/"
        if dialect == "oracle" and not "".join(current).strip():
            if _PLSQL_BLOCK_START.match(script, i):
                match = _PLSQL_BLOCK_END.search(script, i)
                if match:
                    current.append(_strip_comments(script[i : match.start()], dialect))
                    flush()
                    i = match.end()
                    continue

        ch = script[i]

        if script.startswith("--", i):
            end = script.find("\n", i)
            i = n if end < 0 else end
            continue

        if script.startswith("/*", i):
            end = script.find("*/", i + 2)
            i = n if end < 0 else end + 2
            current.append(" ")
            continue

        if ch in ("'", '"', "`") or (ch == "[" and dialect == "sqlserver"):
            closing = "]" if ch == "[" else ch
            end = _find_closing_quote(script, i, closing) if ch != "[" else _find_bracket(script, i)
            end = n - 1 if end < 0 else end
            current.append(script[i : end + 1])
            i = end + 1
            continue

        if ch == "$" and dialect == "postgresql":
            tag = _DOLLAR_TAG.match(script, i)
            if tag:
                end = script.find(tag.group(0), tag.end())
                end = n if end < 0 else end + len(tag.group(0))
                current.append(script[i:end])
                i = end
                continue

        if ch == ";":
            flush()
            i += 1
            continue

        current.append(ch)
        i += 1

    flush()
    return statements


def _find_bracket(text: str, start: int) -> int:
    i = start + 1
    n = len(text)
    while i < n:
        if text[i] == "]":
            if i + 1 < n and text[i + 1] == "]":
                i += 2
                continue
            return i
        i += 1
    return -1


def _strip_comments(block: str, dialect: str) -> str:
    """Elimina comentarios fuera de literales en un bloque, manteniendo el resto."""
    out: List[str] = []
    i = 0
    n = len(block)
    while i < n:
        if block.startswith("--", i):
            end = block.find("\n", i)
            i = n if end < 0 else end
            continue
        if block.startswith("/*", i):
            end = block.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        ch = block[i]
        if ch in ("'", '"'):
            end = _find_closing_quote(block, i, ch)
            end = n - 1 if end < 0 else end
            out.append(block[i : end + 1])
            i = end + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def is_transaction_control(statement: str) -> bool:
    """True si la sentencia controla la transacción (BEGIN, COMMIT, ROLLBACK, ...)."""
    stmt = statement.strip().rstrip(";").strip()
    return bool(_TRANSACTION_CONTROL.match(stmt))
