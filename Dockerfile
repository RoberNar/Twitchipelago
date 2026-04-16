# -- Phase 1: Build the React frontend --
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY panel/package*.json ./
RUN npm ci
COPY panel/ ./
# Cuando Vite compila, las rutas a la API quedarán vacías o dependientes del entorno, lo cual es ideal porque el backend las sirve directas.
RUN npm run build

# -- Phase 2: Python backend serving both API and Frontend --
FROM python:3.11-slim
WORKDIR /app

# Instalar dependencias del SO si fuese necesario para libpq (postgres)
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Instalar los paquetes de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el backend base
COPY . .

# Copiar el frontend empacado (Fase 1) a la carpeta que Flask espera
COPY --from=frontend-builder /app/dist /app/panel/dist

# Exponer el puerto
EXPOSE 5000

# En Railway, PORT se asigna dinámicamente. Usamos "sh -c" para que lea la variable $PORT o recaiga en 5000.
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-5000} server:app"]
