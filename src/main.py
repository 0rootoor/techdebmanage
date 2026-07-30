from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import date, datetime, timedelta
import pandas as pd
import io
import json
import os

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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API Endpoints : Projets ---

@app.post("/api/projects")
def create_project_endpoint(
    name: str,
    description: str = "",
    is_pilot: bool = False,
    app_status: str = "En projet",
    socle: str = "",
    framework: str = "",
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
async def import_projects(file: UploadFile = File(...), db: Session = Depends(get_db)):
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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
    
    db.commit()
    return {"message": "Dette mise à jour avec succès"}

@app.delete("/api/debts/{debt_id}")
def delete_debt_endpoint(debt_id: int, db: Session = Depends(get_db)):
    db_debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    db.delete(db_debt)
    db.commit()
    return {"message": "Dette supprimée"}

@app.patch("/api/debts/{debt_id}/status")
def update_debt_status(debt_id: int, status: str, db: Session = Depends(get_db)):
    db_debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    db_debt.status = status
    db.commit()
    return {"message": "Statut mis à jour"}


# --- Interface Frontend Complète ---

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    projects = db.query(ProjectModel).order_by(ProjectModel.is_pilot.desc(), ProjectModel.name).all()
    debts = db.query(TechDebtModel).all()
    total_cost = sum(d.cost_days for d in debts)
    sorted_debts = sorted(debts, key=lambda x: x.target_date if x.target_date else date.max)

    open_debts = [d for d in debts if d.status != "Résolue"]
    overdue_debts = [d for d in open_debts if d.target_date and d.target_date < date.today()]
    pilot_projects = [p for p in projects if p.is_pilot]

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

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "projects": projects,
            "debts": debts,
            "sorted_debts": sorted_debts,
            "total_cost": total_cost,
            "open_debts_count": len(open_debts),
            "overdue_count": len(overdue_debts),
            "pilot_count": len(pilot_projects),
            "today": date.today(),
            "chart_data_json": json.dumps(chart_data, ensure_ascii=False).replace("</", "<\\/"),
            "gantt_data_json": json.dumps(gantt_rows, ensure_ascii=False).replace("</", "<\\/"),
        },
    )