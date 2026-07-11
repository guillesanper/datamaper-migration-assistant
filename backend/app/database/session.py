"""
SQLAlchemy Session Management

Este módulo configura el engine de SQLAlchemy y proporciona la factory
de sesiones para la aplicación. También incluye la dependencia FastAPI
para inyectar sesiones en los endpoints.

Connection Pooling:
- pool_size=10: Mantiene 10 conexiones abiertas en el pool
- max_overflow=20: Permite hasta 20 conexiones adicionales temporales
- pool_pre_ping=True: Verifica la salud de la conexión antes de usarla
- pool_recycle=3600: Recicla conexiones después de 1 hora

Usage en FastAPI:
    from app.database.session import get_db_session
    from sqlalchemy.orm import Session

    @router.get("/users")
    def get_users(db: Session = Depends(get_db_session)):
        users = db.query(User).all()
        return users
"""

import os
from typing import Generator
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Cargar variables de entorno
load_dotenv(encoding="utf-8")

# Construir URL de conexión PostgreSQL con URL-encoding para manejar caracteres especiales
# Esto es especialmente importante en Windows donde puede haber problemas de encoding
db_user = quote_plus(os.getenv("DB_USER", ""))
db_password = quote_plus(os.getenv("DB_PASSWORD", ""))
db_host = os.getenv("DB_HOST", "localhost")
db_port = os.getenv("DB_PORT", "5432")
db_name = os.getenv("DB_NAME", "datamap_dev")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

# Crear engine con connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=10,  # Número de conexiones a mantener en pool
    max_overflow=20,  # Máximo de conexiones adicionales
    pool_pre_ping=True,  # Verificar conexión antes de usar
    pool_recycle=3600,  # Reciclar conexiones cada 1 hora
    echo=False,  # Set True para logging SQL (solo desarrollo)
    client_encoding="utf8",  # Importante para Windows: encoding explícito
    connect_args={"client_encoding": "utf8"},  # Asegurar UTF-8 en la conexión
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Importante para FastAPI: no expira objetos después de commit
)


def get_db_session() -> Generator[Session, None, None]:
    """
    Dependencia FastAPI para obtener una sesión de SQLAlchemy.

    Esta función crea una nueva sesión para cada request, ejecuta commit
    automático si todo sale bien, o rollback si hay un error, y finalmente
    cierra la sesión.

    Yields:
        Session: Sesión de SQLAlchemy activa

    Example:
        @router.get("/users")
        def get_users(db: Session = Depends(get_db_session)):
            users = db.query(User).all()
            return users

    Note:
        - Auto-commit: Los cambios se guardan automáticamente al finalizar
        - Auto-rollback: Si hay una excepción, hace rollback automático
        - Auto-close: La sesión siempre se cierra, incluso si hay error
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()  # Auto-commit si no hay errores
    except Exception:
        session.rollback()  # Auto-rollback si hay error
        raise  # Re-lanza la excepción para que FastAPI la maneje
    finally:
        session.close()  # Siempre cierra la sesión
