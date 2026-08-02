import os
import secrets
import hashlib
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import UserModel

SESSION_SECRET_KEY = os.environ.get("TECHDEBT_SECRET_KEY", "dev-secret-key-change-in-production")
DEFAULT_ADMIN_PASSWORD = os.environ.get("TECHDEBT_ADMIN_PASSWORD", "changeme123")

ROLES = ["admin", "contributeur", "lecture_seule"]
ROLE_LABELS = {"admin": "Administrateur", "contributeur": "Contributeur", "lecture_seule": "Lecture seule"}

def hash_password(password: str, salt: str = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"{salt}${digest.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, _ = stored_hash.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored_hash)

def require_api_auth(request: Request) -> str:
    """Dépendance pour les endpoints API en lecture ou pour tout utilisateur connecté : lève une 401 JSON si non connecté."""
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Authentification requise")
    return request.session.get("username", "Utilisateur")

def require_contributor(request: Request) -> str:
    """Dépendance pour les actions d'écriture (créer/modifier/supprimer dettes, commentaires, liens...).
    Les comptes en lecture seule sont bloqués."""
    username = require_api_auth(request)
    if request.session.get("role") == "lecture_seule":
        raise HTTPException(status_code=403, detail="Ton compte est en lecture seule : cette action n'est pas autorisée.")
    return username

def require_admin(request: Request) -> str:
    """Dépendance pour les actions d'administration (suppression d'application, gestion des utilisateurs)."""
    username = require_api_auth(request)
    if request.session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Cette action est réservée aux administrateurs.")
    return username
