# ==============================================================================
# DOCKERFILE: AGENTE DE SOPORTE INTELIGENTE
# ==============================================================================

# 1. Partir de una imagen base oficial de Python ligera (Debian slim)
FROM python:3.12-slim

# 2. Forzar a Python a no almacenar en búfer la salida estándar (muestra prints en logs en tiempo real)
ENV PYTHONUNBUFFERED=1

# 3. Establecer la carpeta de trabajo dentro del contenedor
WORKDIR /app

# 4. Copiar únicamente el archivo de dependencias primero (aprovecha la caché de capas de Docker)
COPY requirements.txt .

# 5. Instalar dependencias de Python sin guardar caché de pip para reducir el tamaño final de la imagen
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiar el script de la aplicación a la carpeta de trabajo
COPY agente_soporte.py .

# 7. Punto de entrada principal: permite pasar argumentos adicionales (como --una-vez) en 'docker run'
ENTRYPOINT ["python", "agente_soporte.py"]

