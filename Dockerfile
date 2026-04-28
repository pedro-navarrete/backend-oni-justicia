# Imagen base
FROM python:3.11-slim
ENV TZ=America/El_Salvador
LABEL authors="MJSP"

# Establecer directorio de trabajo
WORKDIR /app

# Copiar todos los archivos del proyecto
COPY . .

# Instalar dependencias
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Exponer puerto
EXPOSE 8000

# Ejecutar usando uvicorn (ya no python main.py)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]