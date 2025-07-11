# Usar Python 3.11 como base (más estable para ML/AI)
FROM python:3.11-slim

# Configurar variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements.txt primero (para optimizar cache de Docker)
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Descargar modelo de spaCy español
RUN python -m spacy download es_core_news_sm

# Copiar código fuente desde la carpeta src/
COPY src/ .

# Copiar assets (logos)
COPY assets/ ./assets/

# Crear directorios necesarios con permisos correctos
RUN mkdir -p output public_downloads temp_uploads static InnAgg/temp_uploads && \
    chmod -R 755 output public_downloads temp_uploads static

# Exponer el puerto 7860 (puerto de Gradio)
EXPOSE 7860

# Variables de entorno para Gradio
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# Healthcheck para verificar que la app funciona
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:7860 || exit 1

# Comando para ejecutar la aplicación
CMD ["python", "gr1.py"] 