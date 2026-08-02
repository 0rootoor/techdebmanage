from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from database import get_db
from models import ProjectModel, TechDebtModel, log_action
from auth import require_contributor, require_admin
import pandas as pd
import io
from datetime import datetime

router = APIRouter(prefix="/api/projects", tags=["projects"])

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

@router.post("")
def create_project_endpoint(
    name: str,
    description: str = "",
    is_pilot: bool = False,
    app_status: str = "En projet",
    socle: str = "",
    framework: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(require_contributor),
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

@router.put("/{project_id}")
def update_project_endpoint(
    project_id: int,
    name: str,
    description: str = "",
    is_pilot: bool = False,
    app_status: str = "En projet",
    socle: str = "",
    framework: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(require_contributor),
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

@router.delete("/{project_id}")
def delete_project_endpoint(project_id: int, db: Session = Depends(get_db), user: str = Depends(require_admin)):
    db_project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="Application non trouvée")
    name = db_project.name
    debt_count = db.query(TechDebtModel).filter(TechDebtModel.project_id == project_id).count()
    db.delete(db_project)  # cascade="all, delete-orphan" supprime aussi les dettes associées
    log_action(db, user, "Application", name, "Suppression",
               f"{debt_count} dette(s) associée(s) supprimée(s) en cascade" if debt_count else None)
    db.commit()
    return {"message": f"Application supprimée" + (f" ainsi que {debt_count} dette(s) associée(s)" if debt_count else "")}

@router.post("/import")
async def import_projects(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: str = Depends(require_contributor),
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
