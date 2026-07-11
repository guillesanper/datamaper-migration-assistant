# Multi-stage build para optimizar tamaño de imagen
FROM python:3.11-slim as builder

# Instalar dependencias de compilación
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements y instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Imagen final (más pequeña)
FROM python:3.11-slim

# Instalar solo las librerías runtime necesarias
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    unixodbc \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root para seguridad
RUN useradd -m -u 1000 datamap && \
    mkdir -p /app && \
    chown -R datamap:datamap /app

# Copiar dependencias de Python desde builder
COPY --from=builder --chown=datamap:datamap /root/.local /home/datamap/.local

# Establecer PATH para que encuentre los paquetes
ENV PATH=/home/datamap/.local/bin:$PATH

# Cambiar a directorio de trabajo
WORKDIR /app

# Copiar código de la aplicación
COPY --chown=datamap:datamap . .

# Cambiar a usuario no-root
USER datamap

# Exponer puerto
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando por defecto (para desarrollo con hot reload)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
