from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Boolean, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import date, datetime, timedelta
import pandas as pd
import io
import json
import os
import urllib.request

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
# Jinja2Templates active déjà l'autoescape HTML par défaut pour les fichiers .html.
# On ajoute un filtre tojson pour pouvoir injecter des valeurs en toute sécurité
# dans les attributs onclick (échappées ensuite en HTML via |e).
templates.env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)

# Configuration de la base de données SQLite
DATABASE_URL = "sqlite:///./tech_debt_v4.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Modèles SQLAlchemy ---

class ProjectModel(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String)
    is_pilot = Column(Boolean, default=False, nullable=False)
    app_status = Column(String, default="En projet")
    socle = Column(String, nullable=True)
    framework = Column(String, nullable=True)

    debts = relationship("TechDebtModel", back_populates="project", cascade="all, delete-orphan")

class TechDebtModel(Base):
    __tablename__ = "tech_debts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    category = Column(String, default="Code")
    impact = Column(String, default="Moyen")
    cost_days = Column(Integer)
    status = Column(String, default="Ouverte")
    created_at = Column(Date, default=date.today)
    start_date = Column(Date, nullable=True)
    target_date = Column(Date, nullable=True)
    assignee = Column(String, nullable=True)
    
    project_id = Column(Integer, ForeignKey("projects.id"))
    project = relationship("ProjectModel", back_populates="debts")

class AuditLogModel(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    username = Column(String)
    entity_type = Column(String)   # "Application" ou "Dette"
    entity_name = Column(String)
    action = Column(String)        # "Création", "Modification", "Suppression", "Changement de statut"
    details = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

# Petite migration de compatibilité : si la base existait déjà (avant l'ajout
# de is_pilot), create_all() ne modifie pas les tables existantes. On ajoute
# la colonne manuellement si besoin. À remplacer par Alembic pour une vraie gestion de schéma.
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

# --- Authentification ---
# Authentification minimale par mot de passe partagé + session signée (cookie).
# Adaptée à un usage en petite équipe interne. Pour un déploiement plus large
# (plusieurs équipes, traçabilité fine par utilisateur, SSO...), il faudra
# remplacer ceci par une vraie gestion de comptes (ex: FastAPI Users, SSO d'entreprise).
APP_PASSWORD = os.environ.get("TECHDEBT_APP_PASSWORD", "changeme123")
SESSION_SECRET_KEY = os.environ.get("TECHDEBT_SECRET_KEY", "dev-secret-key-change-in-production")
if APP_PASSWORD == "changeme123":
    print("⚠️  ATTENTION : mot de passe par défaut utilisé. Définis la variable d'environnement "
          "TECHDEBT_APP_PASSWORD avant tout déploiement au-delà de ton poste.")
if SESSION_SECRET_KEY == "dev-secret-key-change-in-production":
    print("⚠️  ATTENTION : clé de session par défaut utilisée. Définis la variable d'environnement "
          "TECHDEBT_SECRET_KEY avant tout déploiement au-delà de ton poste.")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY, session_cookie="techdebt_session")

# --- Alertes Slack (optionnel) ---
# Si la variable d'environnement TECHDEBT_SLACK_WEBHOOK_URL est définie, un bouton
# permet d'envoyer un résumé des alertes sur Slack. Sans elle, les alertes restent
# visibles uniquement dans l'onglet "Alertes" de l'application.
SLACK_WEBHOOK_URL = os.environ.get("TECHDEBT_SLACK_WEBHOOK_URL", "")

def send_slack_message(text: str) -> bool:
    if not SLACK_WEBHOOK_URL:
        return False
    try:
        data = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(SLACK_WEBHOOK_URL, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        print(f"Échec de l'envoi Slack : {e}")
        return False

def require_api_auth(request: Request) -> str:
    """Dépendance pour les endpoints API : lève une 401 JSON si non connecté."""
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Authentification requise")
    return request.session.get("username", "Utilisateur")

def log_action(db: Session, username: str, entity_type: str, entity_name: str, action: str, details: str = None):
    """Enregistre une entrée dans l'historique. Ne fait pas de commit : à inclure dans la même transaction que l'action elle-même."""
    entry = AuditLogModel(username=username, entity_type=entity_type, entity_name=entity_name, action=action, details=details)
    db.add(entry)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if password == APP_PASSWORD:
        request.session["authenticated"] = True
        request.session["username"] = username.strip() or "Utilisateur"
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Mot de passe incorrect."},
        status_code=401,
    )

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# --- API Endpoints : Projets ---

@app.post("/api/projects")
def create_project_endpoint(
    name: str,
    description: str = "",
    is_pilot: bool = False,
    app_status: str = "En projet",
    socle: str = "",
    framework: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(require_api_auth),
):
    if not name.strip():
        raise HTTPException(status_code=400, detail="Le nom du projet est requis")
    existing = db.query(ProjectModel).filter(ProjectModel.name == name.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ce projet existe déjà")
    
    db_project = ProjectModel(
        name=name.strip(),
        description=description.strip(),
        is_pilot=is_pilot,
        app_status=app_status,
        socle=socle.strip() or None,
        framework=framework.strip() or None,
    )
    db.add(db_project)
    log_action(db, user, "Application", db_project.name, "Création",
               f"Statut : {app_status}" + (f", pilote" if is_pilot else ""))
    db.commit()
    return {"message": "Projet créé avec succès"}

@app.put("/api/projects/{project_id}")
def update_project_endpoint(
    project_id: int,
    name: str,
    description: str = "",
    is_pilot: bool = False,
    app_status: str = "En projet",
    socle: str = "",
    framework: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(require_api_auth),
):
    db_project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="Application non trouvée")
    if not name.strip():
        raise HTTPException(status_code=400, detail="Le nom du projet est requis")
    duplicate = db.query(ProjectModel).filter(ProjectModel.name == name.strip(), ProjectModel.id != project_id).first()
    if duplicate:
        raise HTTPException(status_code=400, detail="Une autre application porte déjà ce nom")

    db_project.name = name.strip()
    db_project.description = description.strip()
    db_project.is_pilot = is_pilot
    db_project.app_status = app_status
    db_project.socle = socle.strip() or None
    db_project.framework = framework.strip() or None
    log_action(db, user, "Application", db_project.name, "Modification",
               f"Statut : {app_status}" + (f", pilote" if is_pilot else ""))
    db.commit()
    return {"message": "Application mise à jour avec succès"}

def _clean_str(value):
    """Nettoie une valeur pandas (NaN, float, etc.) en chaîne, ou None si vide."""
    if pd.isna(value):
        return None
    s = str(value).strip()
    if not s or s.lower() == 'nan':
        return None
    return s

def _parse_excel_date(value):
    """Convertit une date issue d'Excel/CSV (Timestamp, string, etc.) en date Python, ou None."""
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.date() if isinstance(value, datetime) else value.to_pydatetime().date()
    s = str(value).strip()
    if not s or s.lower() == 'nan':
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

VALID_APP_STATUSES = {"En projet", "En développement", "En production", "En maintenance", "Décommissionnée"}
VALID_CATEGORIES = {"Code", "Architecture", "Sécurité", "Documentation", "Tests"}
VALID_IMPACTS = {"Faible", "Moyen", "Élevé"}
VALID_DEBT_STATUSES = {"Ouverte", "En cours", "Résolue"}

@app.post("/api/projects/import")
async def import_projects(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: str = Depends(require_api_auth),
):
    contents = await file.read()
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Format non supporté (.csv ou .xlsx requis)")

        if 'name' not in df.columns:
            raise HTTPException(status_code=400, detail="Le fichier doit contenir une colonne 'name'")

        imported_projects = 0
        imported_debts = 0

        for _, row in df.iterrows():
            name = _clean_str(row.get('name'))
            if not name:
                continue

            # --- Champs de l'application ---
            description = _clean_str(row.get('description')) or ''
            is_pilot_raw = (_clean_str(row.get('is_pilot')) or '').lower()
            is_pilot = is_pilot_raw in ('1', 'true', 'oui', 'yes', 'x')
            app_status = _clean_str(row.get('app_status'))
            if app_status not in VALID_APP_STATUSES:
                app_status = "En projet"
            socle = _clean_str(row.get('socle'))
            framework = _clean_str(row.get('framework'))

            db_project = db.query(ProjectModel).filter(ProjectModel.name == name).first()
            if not db_project:
                db_project = ProjectModel(
                    name=name, description=description, is_pilot=is_pilot,
                    app_status=app_status, socle=socle, framework=framework,
                )
                db.add(db_project)
                db.flush()  # pour obtenir db_project.id avant le commit final
                imported_projects += 1

            # --- Champ(s) de dette technique (optionnels, sur la même ligne) ---
            debt_title = _clean_str(row.get('debt_title'))
            if debt_title:
                category = _clean_str(row.get('debt_category'))
                if category not in VALID_CATEGORIES:
                    category = "Code"
                impact = _clean_str(row.get('debt_impact'))
                if impact not in VALID_IMPACTS:
                    impact = "Moyen"
                status = _clean_str(row.get('debt_status'))
                if status not in VALID_DEBT_STATUSES:
                    status = "Ouverte"
                cost_days_raw = _clean_str(row.get('debt_cost_days'))
                try:
                    cost_days = int(float(cost_days_raw)) if cost_days_raw else 1
                except ValueError:
                    cost_days = 1
                assignee = _clean_str(row.get('debt_assignee'))
                start_date = _parse_excel_date(row.get('debt_start_date'))
                target_date = _parse_excel_date(row.get('debt_target_date'))

                db_debt = TechDebtModel(
                    title=debt_title, category=category, impact=impact, status=status,
                    cost_days=cost_days, assignee=assignee,
                    start_date=start_date, target_date=target_date,
                    project=db_project,
                )
                db.add(db_debt)
                imported_debts += 1

        db.commit()
        message = f"{imported_projects} application(s) importée(s)"
        if imported_debts:
            message += f" et {imported_debts} dette(s) importée(s)"
        message += " avec succès !"
        if imported_projects or imported_debts:
            log_action(db, user, "Import", file.filename, "Import fichier",
                       f"{imported_projects} application(s), {imported_debts} dette(s)")
            db.commit()
        return {"message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur : {str(e)}")

# --- API Endpoints : Dettes Techniques (CRUD complet) ---

@app.post("/api/debts")
def create_debt_endpoint(
    project_id: int,
    title: str,
    category: str,
    impact: str,
    cost_days: int,
    assignee: str = "",
    start_date: str = "",
    target_date: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(require_api_auth),
):
    start = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    target = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else None
    db_debt = TechDebtModel(
        title=title,
        category=category,
        impact=impact,
        cost_days=cost_days,
        assignee=assignee if assignee else None,
        start_date=start,
        target_date=target,
        project_id=project_id
    )
    db.add(db_debt)
    log_action(db, user, "Dette", title, "Création", f"{category} / {impact} / {cost_days}j")
    db.commit()
    return {"message": "Dette ajoutée avec succès"}

@app.put("/api/debts/{debt_id}")
def update_debt_endpoint(
    debt_id: int,
    project_id: int,
    title: str,
    category: str,
    impact: str,
    cost_days: int,
    assignee: str = "",
    start_date: str = "",
    target_date: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(require_api_auth),
):
    db_debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    
    start = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    target = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else None
    db_debt.project_id = project_id
    db_debt.title = title
    db_debt.category = category
    db_debt.impact = impact
    db_debt.cost_days = cost_days
    db_debt.assignee = assignee if assignee else None
    db_debt.start_date = start
    db_debt.target_date = target
    log_action(db, user, "Dette", title, "Modification", f"{category} / {impact} / {cost_days}j")
    db.commit()
    return {"message": "Dette mise à jour avec succès"}

@app.delete("/api/debts/{debt_id}")
def delete_debt_endpoint(debt_id: int, db: Session = Depends(get_db), user: str = Depends(require_api_auth)):
    db_debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    title = db_debt.title
    db.delete(db_debt)
    log_action(db, user, "Dette", title, "Suppression")
    db.commit()
    return {"message": "Dette supprimée"}

@app.patch("/api/debts/{debt_id}/status")
def update_debt_status(debt_id: int, status: str, db: Session = Depends(get_db), user: str = Depends(require_api_auth)):
    db_debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    old_status = db_debt.status
    db_debt.status = status
    log_action(db, user, "Dette", db_debt.title, "Changement de statut", f"{old_status} → {status}")
    db.commit()
    return {"message": "Statut mis à jour"}


@app.get("/api/debts/export")
def export_debts(
    ids: str = "",
    format: str = "xlsx",
    db: Session = Depends(get_db),
    user: str = Depends(require_api_auth),
):
    query = db.query(TechDebtModel)
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        if id_list:
            query = query.filter(TechDebtModel.id.in_(id_list))
    debts = query.all()

    rows = []
    for d in debts:
        rows.append({
            "Application": d.project.name if d.project else "",
            "Statut app": d.project.app_status if d.project else "",
            "Socle": d.project.socle if d.project and d.project.socle else "",
            "Framework": d.project.framework if d.project and d.project.framework else "",
            "Pilote": "Oui" if d.project and d.project.is_pilot else "Non",
            "Titre dette": d.title,
            "Catégorie": d.category,
            "Impact": d.impact,
            "Statut dette": d.status,
            "Charge (jours)": d.cost_days,
            "Responsable": d.assignee or "",
            "Date de début": d.start_date.isoformat() if d.start_date else "",
            "Date cible": d.target_date.isoformat() if d.target_date else "",
        })
    df = pd.DataFrame(rows, columns=[
        "Application", "Statut app", "Socle", "Framework", "Pilote", "Titre dette",
        "Catégorie", "Impact", "Statut dette", "Charge (jours)", "Responsable",
        "Date de début", "Date cible",
    ])

    buffer = io.BytesIO()
    if format == "csv":
        df.to_csv(buffer, index=False, encoding="utf-8-sig")
        media_type = "text/csv"
        filename = "registre_dette_technique.csv"
    else:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Dettes")
            worksheet = writer.sheets["Dettes"]
            for col_idx, col_name in enumerate(df.columns, start=1):
                max_len = max([len(str(col_name))] + [len(str(v)) for v in df[col_name].astype(str)]) if len(df) else len(col_name)
                worksheet.column_dimensions[worksheet.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 40)
            for cell in worksheet[1]:
                cell.font = cell.font.copy(bold=True)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "registre_dette_technique.xlsx"

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/alerts/send")
def send_alerts_endpoint(db: Session = Depends(get_db), user: str = Depends(require_api_auth)):
    if not SLACK_WEBHOOK_URL:
        return {
            "sent": False,
            "message": "Aucun webhook Slack configuré (variable d'environnement TECHDEBT_SLACK_WEBHOOK_URL absente). "
                       "Les alertes restent visibles dans l'onglet Alertes de l'application."
        }

    debts = db.query(TechDebtModel).all()
    open_debts = [d for d in debts if d.status != "Résolue"]
    overdue = [d for d in open_debts if d.target_date and d.target_date < date.today()]
    soon_threshold = date.today() + timedelta(days=7)
    soon = [d for d in open_debts if d.target_date and date.today() <= d.target_date <= soon_threshold]
    stale_pilot = [
        d for d in open_debts
        if d.project and d.project.is_pilot and d.status == "Ouverte"
        and (date.today() - (d.start_date or d.created_at or date.today())).days > 30
    ]

    if not overdue and not soon and not stale_pilot:
        return {"sent": False, "message": "Aucune alerte à signaler pour le moment."}

    lines = [f"*Alertes dette technique — {date.today().isoformat()}*"]
    if overdue:
        lines.append(f"\n:red_circle: *{len(overdue)} dette(s) en retard*")
        for d in overdue[:10]:
            lines.append(f"• {d.title} ({d.project.name if d.project else '?'}) — échéance {d.target_date.isoformat()}")
    if soon:
        lines.append(f"\n:large_orange_circle: *{len(soon)} échéance(s) dans les 7 prochains jours*")
        for d in soon[:10]:
            lines.append(f"• {d.title} ({d.project.name if d.project else '?'}) — échéance {d.target_date.isoformat()}")
    if stale_pilot:
        lines.append(f"\n:large_blue_circle: *{len(stale_pilot)} dette(s) pilote(s) ouverte(s) depuis plus de 30 jours*")
        for d in stale_pilot[:10]:
            lines.append(f"• {d.title} ({d.project.name if d.project else '?'})")

    ok = send_slack_message("\n".join(lines))
    if ok:
        log_action(db, user, "Alertes", "Slack", "Envoi", f"{len(overdue)} retard(s), {len(soon)} proche(s), {len(stale_pilot)} pilote(s) bloquée(s)")
        db.commit()
        return {"sent": True, "message": "Alertes envoyées sur Slack avec succès."}
    return {"sent": False, "message": "Échec de l'envoi sur Slack. Vérifie l'URL du webhook et la connexion réseau."}


# --- Interface Frontend Complète ---

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    if not request.session.get("authenticated"):
        return RedirectResponse(url="/login", status_code=303)
    current_user = request.session.get("username", "Utilisateur")

    projects = db.query(ProjectModel).order_by(ProjectModel.is_pilot.desc(), ProjectModel.name).all()
    debts = db.query(TechDebtModel).all()
    total_cost = sum(d.cost_days for d in debts)
    sorted_debts = sorted(debts, key=lambda x: x.target_date if x.target_date else date.max)

    open_debts = [d for d in debts if d.status != "Résolue"]
    overdue_debts = [d for d in open_debts if d.target_date and d.target_date < date.today()]
    pilot_projects = [p for p in projects if p.is_pilot]

    distinct_socles = sorted({p.socle for p in projects if p.socle})
    distinct_frameworks = sorted({p.framework for p in projects if p.framework})

    # Agrégats pour les graphiques (calculés côté serveur, injectés en JSON dans le template)
    categories = ["Code", "Architecture", "Sécurité", "Documentation", "Tests"]
    category_labels, category_counts = [], []
    for cat in categories:
        count = sum(1 for d in debts if d.category == cat)
        if count > 0:
            category_labels.append(cat)
            category_counts.append(count)

    impact_order = ["Faible", "Moyen", "Élevé"]
    impact_counts = [sum(1 for d in debts if d.impact == level) for level in impact_order]

    status_order = ["Ouverte", "En cours", "Résolue"]
    status_counts = [sum(1 for d in debts if d.status == s) for s in status_order]

    cost_by_category = []
    for cat in category_labels:
        cost_by_category.append(sum(d.cost_days for d in debts if d.category == cat))

    chart_data = {
        "categoryLabels": category_labels,
        "categoryCounts": category_counts,
        "costByCategory": cost_by_category,
        "impactLabels": impact_order,
        "impactCounts": impact_counts,
        "statusLabels": status_order,
        "statusCounts": status_counts,
    }

    # Données pour la vue Gantt : une barre par dette, du jour de création
    # jusqu'à la date cible (ou, à défaut, une estimation création + charge en jours).
    gantt_rows = []
    for d in debts:
        start = d.start_date or d.created_at or date.today()
        if d.target_date:
            end = d.target_date
            estimated = False
        else:
            end = start + timedelta(days=max(d.cost_days, 1))
            estimated = True
        if end < start:
            end = start
        gantt_rows.append({
            "id": d.id,
            "title": d.title,
            "project": d.project.name if d.project else "Inconnu",
            "isPilot": bool(d.project and d.project.is_pilot),
            "status": d.status,
            "impact": d.impact,
            "assignee": d.assignee or "Non assigné",
            "costDays": d.cost_days,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "estimated": estimated,
        })
    # Tri : applications pilotes d'abord, puis par date de début
    gantt_rows.sort(key=lambda r: (not r["isPilot"], r["start"]))

    # Vue "portefeuille applicatif" : agrégats par application plutôt que par dette
    portfolio_rows = []
    for p in projects:
        p_debts = [d for d in debts if d.project_id == p.id]
        p_overdue = sum(1 for d in p_debts if d.target_date and d.target_date < date.today() and d.status != "Résolue")
        portfolio_rows.append({
            "project": p,
            "debt_count": len(p_debts),
            "total_cost": sum(d.cost_days for d in p_debts),
            "open_count": sum(1 for d in p_debts if d.status == "Ouverte"),
            "in_progress_count": sum(1 for d in p_debts if d.status == "En cours"),
            "resolved_count": sum(1 for d in p_debts if d.status == "Résolue"),
            "overdue_count": p_overdue,
        })
    portfolio_rows.sort(key=lambda r: (not r["project"].is_pilot, -r["total_cost"]))

    # Alertes : échéances dépassées, échéances proches (7 jours), dettes pilotes bloquées (30 jours)
    SOON_DAYS = 7
    STALE_PILOT_DAYS = 30
    soon_threshold = date.today() + timedelta(days=SOON_DAYS)
    alerts_overdue = [d for d in overdue_debts]
    alerts_soon = [
        d for d in open_debts
        if d.target_date and date.today() <= d.target_date <= soon_threshold
    ]
    alerts_stale_pilot = [
        d for d in open_debts
        if d.project and d.project.is_pilot and d.status == "Ouverte"
        and (date.today() - (d.start_date or d.created_at or date.today())).days > STALE_PILOT_DAYS
    ]

    # Historique récent (200 dernières actions, les plus récentes en premier)
    recent_audit_log = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(200).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "current_user": current_user,
            "projects": projects,
            "debts": debts,
            "sorted_debts": sorted_debts,
            "total_cost": total_cost,
            "open_debts_count": len(open_debts),
            "overdue_count": len(overdue_debts),
            "pilot_count": len(pilot_projects),
            "distinct_socles": distinct_socles,
            "distinct_frameworks": distinct_frameworks,
            "today": date.today(),
            "chart_data_json": json.dumps(chart_data, ensure_ascii=False).replace("</", "<\\/"),
            "gantt_data_json": json.dumps(gantt_rows, ensure_ascii=False).replace("</", "<\\/"),
            "portfolio_rows": portfolio_rows,
            "alerts_overdue": alerts_overdue,
            "alerts_soon": alerts_soon,
            "alerts_stale_pilot": alerts_stale_pilot,
            "soon_days": SOON_DAYS,
            "stale_pilot_days": STALE_PILOT_DAYS,
            "recent_audit_log": recent_audit_log,
            "slack_configured": bool(SLACK_WEBHOOK_URL),
        },
    )