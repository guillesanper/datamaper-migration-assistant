"""
Test estático: DBConnectionService._get_adapter es la única fábrica de adaptadores.

Toda conexión a una BD externa debe pasar por un solo punto, de modo que la política TLS
se aplique (y se pueda vigilar) en un único sitio. Instanciar un adaptador directamente
desde un router o servicio crearía un camino que se salta esa política.
"""

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3] / "app"

ADAPTER_CLASSES = {
    "PostgreSQLAdapter",
    "MySQLAdapter",
    "SQLServerAdapter",
    "OracleAdapter",
}

# Único módulo fuera de utils/db_adapters que puede instanciar adaptadores
FACTORY_MODULE = Path("services") / "db_connection_service.py"


def _instantiations(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in ADAPTER_CLASSES:
            yield node.lineno, name


def test_solo_la_fabrica_instancia_adaptadores():
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        relative = path.relative_to(APP_DIR)
        if relative.parts[:2] == ("utils", "db_adapters") or relative == FACTORY_MODULE:
            continue
        offenders.extend(f"{relative}:{line} {name}(...)" for line, name in _instantiations(path))

    assert (
        not offenders
    ), "Los adaptadores solo se instancian desde DBConnectionService._get_adapter: " + ", ".join(
        offenders
    )


def test_la_fabrica_conserva_los_cuatro_dialectos():
    """Si la fábrica deja de instanciar uno de los adaptadores, este test lo detecta."""
    found = {name for _, name in _instantiations(APP_DIR / FACTORY_MODULE)}

    assert found == ADAPTER_CLASSES
