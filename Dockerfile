# Usar una imagen base oficial de Python 3.9
FROM python:3.9-slim

# Establecer el directorio de trabajo en el contenedor
WORKDIR /app

# Copiar los archivos de requisitos primero para aprovechar la caché de Docker
COPY ./requirements.txt /code/requirements.txt

# Instalar las dependencias de la aplicación
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copiar el resto del código de la aplicación
COPY ./ ./app

# Comando para ejecutar la aplicación usando Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]