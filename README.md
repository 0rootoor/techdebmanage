# 🚀 TechDebt Manager Pro

Un tableau de bord moderne et complet pour suivre, gérer, planifier et importer la dette technique de vos applications et projets.

---

## ✨ Fonctionnalités principales

* **Gestion des applications (Projets)** : Ajout, suivi et identification des applications pilotes.
* **Gestion des dettes techniques** : Déclaration, modification, suivi du statut (*Ouverte*, *En cours*, *Résolue*), catégorisation (Code Legacy, Architecture, Sécurité, etc.) et gestion des impacts (Faible, Moyen, Élevé).
* **Contrôles de cohérence** :
* Unicité des noms d'applications (insensible à la casse).
* Validation temporelle : interdiction de saisir une date cible antérieure à la date de début.


* **Planification & Visualisation** :
* Un **diagramme de Gantt** intégré pour visualiser graphiquement les périodes de résolution.
* Une liste chronologique des échéances.


* **Import de données** : Importation groupée d'applications à partir de fichiers **CSV** ou **Excel (`.xlsx`, `.xls`)**.

---

## 🛠️ Prérequis techniques

* **Python** 3.9 ou supérieur
* **uvicorn** (serveur ASGI)
* **FastAPI**
* **SQLAlchemy** (Base de données SQLite)
* **Pandas** & **OpenPyXL** (pour la gestion des imports de fichiers)

---

## 📦 Installation et Dépendances

1. Assurez-vous d'avoir installé les paquets nécessaires dans votre environnement :
```bash
pip install fastapi uvicorn sqlalchemy pandas openpyxl

```


*(Ou créez un fichier `requirements.txt` contenant ces dépendances).*

---

## 🚀 Lancement de l'application

Placez le code dans un fichier nommé `main.py`, puis lancez le serveur avec l'une des commandes suivantes :

* **Via Python (recommandé si `uvicorn` est installé globalement ou via module) :**
```bash
python -m uvicorn main:app --reload

```


* **Via `uv` (si vous utilisez l'outil de gestion Astral) :**
```bash
uv run uvicorn main:app --reload

```



Une fois le serveur démarré, rendez-vous dans votre navigateur à l'adresse :
👉 **[http://127.0.0.1:8000]
