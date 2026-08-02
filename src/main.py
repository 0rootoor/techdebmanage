import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text

from database import engine, Base, SessionLocal
from models import UserModel
from auth import SESSION_SECRET_KEY, DEFAULT_ADMIN_PASSWORD, hash_password
from routers.views import router as views_router
from routers.projects import router as projects_router
from routers.debts import router as debts_router
from routers.milestones import router as milestones_router

# --- Base de données Bootstrap & Migrations ---
Base.metadata.create_all(bind=engine)

with engine.connect() as conn:
    existing_columns = [row[1] for row in conn.execute(text("PRAGMA table_info(projects)"))]
    if "is_pilot" not in existing_columns:
        conn.execute(text("ALTER TABLE projects ADD COLUMN is_pilot BOOLEAN NOT NULL DEFAULT 0"))
        conn.commit()
    if "app_status" not in existing_columns:
        conn.execute(text("ALTER TABLE projects ADD COLUMN app_status VARCHAR DEFAULT 'En projet'"))
        conn.commit()
    if "socle" not in existing_columns:
        conn.execute(text("ALTER TABLE projects ADD COLUMN socle VARCHAR"))
        conn.commit()
    if "framework" not in existing_columns:
        conn.execute(text("ALTER TABLE projects ADD COLUMN framework VARCHAR"))
        conn.commit()

    existing_debt_columns = [row[1] for row in conn.execute(text("PRAGMA table_info(tech_debts)"))]
    if "start_date" not in existing_debt_columns:
        conn.execute(text("ALTER TABLE tech_debts ADD COLUMN start_date DATE"))
        conn.commit()

# --- Application FastAPI ---
app = FastAPI(title="Gestion Avancée de la Dette Technique")

# Serveur de fichiers statiques (CSS, JS)
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Middleware de session
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY, session_cookie="techdebt_session")

# Bootstrap de l'utilisateur admin par défaut
with SessionLocal() as _bootstrap_db:
    if _bootstrap_db.query(UserModel).count() == 0:
        _bootstrap_db.add(UserModel(username="admin", password_hash=hash_password(DEFAULT_ADMIN_PASSWORD), role="admin"))
        _bootstrap_db.commit()
        if DEFAULT_ADMIN_PASSWORD == "changeme123":
            print("[WARNING] ATTENTION : compte admin créé avec le mot de passe par défaut 'changeme123' "
                  "(identifiant : admin). Change-le dès la première connexion, ou définis "
                  "TECHDEBT_ADMIN_PASSWORD avant le premier démarrage.")

# --- Inclusion des Routeurs ---
app.include_router(views_router)
app.include_router(projects_router)
app.include_router(debts_router)
app.include_router(milestones_router)