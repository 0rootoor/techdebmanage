# Image de base Python légère
FROM python:3.11-slim

# Définition du dossier de travail
WORKDIR /app

# Installation des dépendances système nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copie des fichiers de dépendance
COPY requirements.txt .

# Installation des dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source dans le conteneur
COPY src/ ./src/

# Exposition du port par défaut de l'application
EXPOSE 8000

# Variables d'environnement par défaut
ENV HOST=0.0.0.0
ENV PORT=8000

# Commande de démarrage de l'application FastAPI
CMD ["sh", "-c", "uvicorn src.main:app --host $HOST --port $PORT"]
