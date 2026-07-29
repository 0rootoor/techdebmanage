from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Boolean, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import date, datetime, timedelta
import pandas as pd
import io

# Configuration de la base de données SQLite
DATABASE_URL = "sqlite:///./tech_debt_v8.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Modèles SQLAlchemy ---

class ProjectModel(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String)
    is_pilot = Column(Boolean, default=False)
    
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
def create_project_endpoint(name: str, description: str = "", is_pilot: bool = False, db: Session = Depends(get_db)):
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Le nom du projet est requis")
    
    existing = db.query(ProjectModel).filter(func.lower(ProjectModel.name) == clean_name.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Une application nommée '{existing.name}' existe déjà !")
    
    db_project = ProjectModel(name=clean_name, description=description.strip(), is_pilot=is_pilot)
    db.add(db_project)
    db.commit()
    return {"message": "Projet créé avec succès"}

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

        imported_count = 0
        for _, row in df.iterrows():
            name = str(row['name']).strip()
            if not name or name.lower() == 'nan':
                continue
            description = str(row.get('description', '')).strip()
            if description.lower() == 'nan':
                description = ''
            
            is_pilot_val = False
            if 'is_pilot' in df.columns:
                val = str(row['is_pilot']).strip().lower()
                if val in ['true', '1', 'oui', 'yes']:
                    is_pilot_val = True

            existing = db.query(ProjectModel).filter(func.lower(ProjectModel.name) == name.lower()).first()
            if not existing:
                db_project = ProjectModel(name=name, description=description, is_pilot=is_pilot_val)
                db.add(db_project)
                imported_count += 1

        db.commit()
        return {"message": f"{imported_count} application(s) importée(s) avec succès !"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur : {str(e)}")

# --- API Endpoints : Dettes Techniques ---

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
    
    if start and target and target < start:
        raise HTTPException(status_code=400, detail="La date cible doit être supérieure ou égale à la date de début.")

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
    
    if start and target and target < start:
        raise HTTPException(status_code=400, detail="La date cible doit être supérieure ou égale à la date de début.")
    
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
def read_root(db: Session = Depends(get_db)):
    projects = db.query(ProjectModel).all()
    debts = db.query(TechDebtModel).all()
    total_cost = sum(d.cost_days for d in debts)
    
    project_options = "".join([f'<option value="{p.id}">{p.name} {"(Pilote)" if p.is_pilot else ""}</option>' for p in projects])
    
    # Tableau des Dettes
    debts_rows = ""
    for d in debts:
        p_name = d.project.name if d.project else "Inconnu"
        is_pilot = d.project.is_pilot if d.project else False
        pilot_badge = '<span class="ml-1 px-1.5 py-0.5 rounded text-[10px] bg-purple-100 text-purple-700 font-bold">Pilote</span>' if is_pilot else ''
        
        badge_color = "bg-rose-100 text-rose-700" if d.impact == "Élevé" else ("bg-amber-100 text-amber-700" if d.impact == "Moyen" else "bg-emerald-100 text-emerald-700")
        start_date_str = d.start_date.strftime("%Y-%m-%d") if d.start_date else ""
        target_date_str = d.target_date.strftime("%Y-%m-%d") if d.target_date else ""
        
        debts_rows += f"""
        <tr class="border-b hover:bg-slate-50 debt-row" data-pilot="{str(is_pilot).lower()}">
            <td class="p-3">
                <div class="font-semibold text-slate-800">{d.title}</div>
                <div class="text-xs text-blue-600 font-medium">📦 {p_name} {pilot_badge}</div>
            </td>
            <td class="p-3">
                <span class="inline-block px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-700 mr-1">{d.category}</span>
                <span class="px-2 py-0.5 rounded text-xs font-semibold {badge_color}">{d.impact}</span>
            </td>
            <td class="p-3 text-xs text-slate-600">
                <div class="font-medium text-slate-800">{d.cost_days} jours</div>
                <div class="text-indigo-600">👤 {d.assignee or 'Non assigné'}</div>
            </td>
            <td class="p-3">
                <select onchange="updateStatus({d.id}, this.value)" class="border rounded p-1 text-xs bg-white">
                    <option value="Ouverte" {'selected' if d.status == 'Ouverte' else ''}>Ouverte</option>
                    <option value="En cours" {'selected' if d.status == 'En cours' else ''}>En cours</option>
                    <option value="Résolue" {'selected' if d.status == 'Résolue' else ''}>Résolue</option>
                </select>
            </td>
            <td class="p-3 text-right space-x-1">
                <button onclick="openEditDebt({d.id}, {d.project_id}, `{d.title}`, `{d.category}`, `{d.impact}`, {d.cost_days}, `{d.assignee or ''}`, `{start_date_str}`, `{target_date_str}`)" class="px-2 py-1 bg-amber-50 text-amber-700 rounded text-xs border border-amber-200 hover:bg-amber-100">Modifier</button>
                <button onclick="deleteDebt({d.id})" class="px-2 py-1 bg-rose-50 text-rose-700 rounded text-xs border border-rose-200 hover:bg-rose-100">Supprimer</button>
            </td>
        </tr>
        """
    if not debts:
        debts_rows = '<tr><td colspan="5" class="p-8 text-center text-slate-400">Aucune dette enregistrée pour le moment.</td></tr>'

    # Planning & Gantt Generator
    sorted_debts = sorted(debts, key=lambda x: x.target_date if x.target_date else date.max)
    planning_cards = ""
    gantt_rows = ""
    
    valid_dates = [d.target_date for d in debts if d.target_date] + [d.start_date for d in debts if d.start_date]
    if valid_dates:
        min_date = min(valid_dates) - timedelta(days=3)
        max_date = max(valid_dates) + timedelta(days=7)
        total_days_span = (max_date - min_date).days or 1
    else:
        min_date = date.today()
        max_date = date.today() + timedelta(days=30)
        total_days_span = 30

    for d in sorted_debts:
        p_name = d.project.name if d.project else "Inconnu"
        is_pilot = d.project.is_pilot if d.project else False
        start_str = d.start_date.strftime("%Y-%m-%d") if d.start_date else "Non définie"
        target_str = d.target_date.strftime("%Y-%m-%d") if d.target_date else "Non planifiée"
        
        planning_cards += f"""
        <div class="p-4 border rounded-lg flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-slate-50">
            <div class="space-y-1">
                <div class="flex items-center gap-2">
                    <span class="text-xs font-bold px-2 py-0.5 bg-blue-100 text-blue-700 rounded">{p_name}</span>
                    { '<span class="text-[10px] bg-purple-100 text-purple-700 font-bold px-1.5 py-0.5 rounded">Pilote</span>' if is_pilot else '' }
                    <span class="text-sm font-bold text-slate-800">{d.title}</span>
                </div>
                <div class="text-xs text-slate-500 flex gap-4">
                    <span>Charge : <strong>{d.cost_days}j</strong></span>
                    <span>Responsable : <strong class="text-indigo-600">{d.assignee or 'Non assigné'}</strong></span>
                    <span>Statut : <strong>{d.status}</strong></span>
                </div>
            </div>
            <div class="text-right text-xs">
                <span class="text-slate-400">Du {start_str} au </span>
                <span class="font-bold text-rose-600">{target_str}</span>
            </div>
        </div>
        """

        # Ligne Diagramme de Gantt
        if d.target_date or d.start_date:
            end_d = d.target_date if d.target_date else (d.start_date + timedelta(days=d.cost_days))
            start_d = d.start_date if d.start_date else (end_d - timedelta(days=d.cost_days))
            if start_d < min_date:
                start_d = min_date
            
            left_percent = max(0, min(100, ((start_d - min_date).days / total_days_span) * 100))
            duration_days = (end_d - start_d).days or 1
            width_percent = max(2, min(100 - left_percent, (duration_days / total_days_span) * 100))
            
            if is_pilot:
                bar_color = "bg-purple-600"
            else:
                bar_color = "bg-emerald-500" if d.status == "Résolue" else ("bg-blue-500" if d.status == "En cours" else "bg-indigo-500")
            
            gantt_rows += f"""
            <div class="flex items-center py-2 border-b border-slate-100 text-xs">
                <div class="w-1/4 truncate font-medium text-slate-700 pr-2" title="{d.title} ({p_name})">
                    <span class="{'text-purple-600 font-bold' if is_pilot else 'text-blue-600 font-semibold'}">[{p_name}{' 🎯' if is_pilot else ''}]</span> {d.title}
                </div>
                <div class="w-3/4 relative h-6 bg-slate-100 rounded flex items-center">
                    <div style="left: {left_percent}%; width: {width_percent}%;" 
                         class="absolute h-4 {bar_color} rounded shadow-sm text-[10px] text-white px-1 flex items-center justify-between truncate"
                         title="{'[PILOTE] ' if is_pilot else ''}Début: {start_d.strftime('%Y-%m-%d')} | Fin: {end_d.strftime('%Y-%m-%d')} | Charge: {d.cost_days}j">
                        <span class="truncate">{d.cost_days}j</span>
                    </div>
                </div>
            </div>
            """

    if not debts:
        planning_cards = '<div class="text-center text-slate-400 py-6">Aucune dette à planifier.</div>'
        gantt_rows = '<div class="text-center text-slate-400 py-6">Aucune donnée pour le Gantt.</div>'

    html_content = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Gestionnaire Pro & Dette Technique</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 min-h-screen p-6">
    <div class="max-w-6xl mx-auto space-y-8">
        
        <!-- En-tête -->
        <header class="flex justify-between items-center bg-white p-6 rounded-xl shadow-sm border border-slate-200">
            <div>
                <h1 class="text-2xl font-bold text-slate-800">🚀 TechDebt Manager Pro</h1>
                <p class="text-sm text-slate-500">Suivi des applications, projets, planification et import Excel</p>
            </div>
            <div class="flex gap-4 items-center">
                <div class="text-right">
                    <p class="text-xs text-slate-400">Total Dettes</p>
                    <p class="text-xl font-bold text-blue-600">DEBTS_COUNT_PLACEHOLDER</p>
                </div>
                <div class="text-right border-l pl-4">
                    <p class="text-xs text-slate-400">Charge Totale</p>
                    <p class="text-xl font-bold text-amber-600">TOTAL_COST_PLACEHOLDER jours</p>
                </div>
            </div>
        </header>

        <!-- Navigation par onglets & Filtres rapides -->
        <div class="flex justify-between items-center border-b pb-2">
            <div class="flex gap-2">
                <button onclick="switchTab('register')" id="btn-register" class="px-4 py-2 rounded font-medium text-sm bg-blue-600 text-white">Registre & Saisie</button>
                <button onclick="switchTab('planning')" id="btn-planning" class="px-4 py-2 rounded font-medium text-sm bg-white text-slate-600 border">📅 Planning & Gantt</button>
            </div>
            <div class="flex items-center gap-2 bg-white px-3 py-1.5 rounded-lg border text-xs">
                <label class="font-medium text-slate-600">Filtre :</label>
                <select id="filterPilot" onchange="filterTable()" class="border rounded p-1 bg-slate-50 text-slate-700">
                    <option value="all">Toutes les applications</option>
                    <option value="pilot">Applications Pilotes uniquement</option>
                </select>
            </div>
        </div>

        <!-- ONGLET 1 : REGISTRE ET SAISIE -->
        <div id="tab-register" class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="space-y-6">
                <!-- Ajouter Application -->
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-4">📂 Ajouter une Application</h2>
                    <form onsubmit="event.preventDefault(); createProject(this);" class="space-y-4">
                        <input name="name" type="text" placeholder="Nom de l'application" class="w-full border p-2 rounded text-sm" required />
                        <textarea name="description" placeholder="Courte description..." class="w-full border p-2 rounded text-sm" rows="2"></textarea>
                        <div class="flex items-center gap-2">
                            <input name="is_pilot" type="checkbox" id="is_pilot_checkbox" value="true" class="w-4 h-4 text-blue-600 rounded border-gray-300" />
                            <label for="is_pilot_checkbox" class="text-xs font-medium text-slate-700">Définir comme application pilote</label>
                        </div>
                        <button type="submit" class="w-full bg-slate-800 text-white py-2 rounded text-sm font-medium hover:bg-slate-700">Enregistrer l'App</button>
                    </form>
                    <p id="projectMessage" class="text-xs mt-3 font-medium"></p>
                </div>

                <!-- Import Excel / CSV -->
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-2">📊 Importer depuis Excel / CSV</h2>
                    <p class="text-xs text-slate-500 mb-4">Colonnes supportées : <code class="bg-slate-100 p-0.5 rounded font-bold">name</code>, <code class="bg-slate-100 p-0.5 rounded font-bold">description</code>, <code class="bg-slate-100 p-0.5 rounded font-bold">is_pilot</code> (true/false).</p>
                    <form onsubmit="event.preventDefault(); uploadFile();" class="space-y-4">
                        <input type="file" id="fileInput" accept=".xlsx, .xls, .csv" class="w-full text-sm border p-2 rounded file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700" required />
                        <button type="submit" class="w-full bg-emerald-600 text-white py-2 rounded text-sm font-medium hover:bg-emerald-700">Lancer l'import</button>
                    </form>
                    <p id="importMessage" class="text-xs mt-3 font-medium text-emerald-600"></p>
                </div>

                <!-- Formulaire Déclarer / Modifier une Dette -->
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 id="debt-form-title" class="text-lg font-semibold text-slate-700 mb-4">⚠️ Déclarer une Dette</h2>
                    <form onsubmit="event.preventDefault(); saveDebt(this);" class="space-y-4">
                        <input type="hidden" id="debt_id" name="debt_id" value="" />
                        <select name="project_id" id="debt_project_id" class="w-full border p-2 rounded text-sm" required>
                            <option disabled selected value="">Sélectionner une application</option>
                            PROJECT_OPTIONS_PLACEHOLDER
                        </select>
                        <input name="title" id="debt_title" type="text" placeholder="Intitulé de la dette" class="w-full border p-2 rounded text-sm" required />
                        
                        <div class="grid grid-cols-2 gap-2">
                            <select name="category" id="debt_category" class="border p-2 rounded text-sm">
                                <option value="Code">Code Legacy</option>
                                <option value="Architecture">Architecture</option>
                                <option value="Sécurité">Sécurité</option>
                                <option value="Documentation">Documentation</option>
                                <option value="Tests">Manque de tests</option>
                            </select>
                            <select name="impact" id="debt_impact" class="border p-2 rounded text-sm">
                                <option value="Faible">Impact Faible</option>
                                <option value="Moyen" selected>Impact Moyen</option>
                                <option value="Élevé">Impact Élevé</option>
                            </select>
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <input name="cost_days" id="debt_cost_days" type="number" placeholder="Coût (jours)" class="border p-2 rounded text-sm" required />
                            <input name="assignee" id="debt_assignee" type="text" placeholder="Responsable" class="border p-2 rounded text-sm" />
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-[11px] text-slate-500 mb-1">Date début :</label>
                                <input name="start_date" id="debt_start_date" type="date" onchange="updateMinTargetDate()" class="w-full border p-2 rounded text-sm" />
                            </div>
                            <div>
                                <label class="block text-[11px] text-slate-500 mb-1">Date cible :</label>
                                <input name="target_date" id="debt_target_date" type="date" class="w-full border p-2 rounded text-sm" />
                            </div>
                        </div>

                        <div class="flex gap-2">
                            <button type="submit" id="debt-submit-btn" class="flex-1 bg-blue-600 text-white py-2 rounded text-sm font-medium hover:bg-blue-700">Ajouter la dette</button>
                            <button type="button" id="debt-cancel-btn" onclick="resetDebtForm()" class="hidden px-3 bg-slate-200 text-slate-700 rounded text-sm font-medium hover:bg-slate-300">Annuler</button>
                        </div>
                    </form>
                    <p id="debtMessage" class="text-xs mt-3 font-medium"></p>
                </div>
            </div>

            <!-- Registre des Dettes (Tableau) -->
            <div class="lg:col-span-2 space-y-6">
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-4">📋 Registre des Dettes Techniques</h2>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-sm">
                            <thead>
                                <tr class="bg-slate-50 border-b text-slate-500">
                                    <th class="p-3">App / Titre</th>
                                    <th class="p-3">Catégorie / Impact</th>
                                    <th class="p-3">Charge & Resp.</th>
                                    <th class="p-3">Statut</th>
                                    <th class="p-3 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody id="debtsTableBody">
                                DEBTS_ROWS_PLACEHOLDER
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- ONGLET 2 : PLANNING & GANTT -->
        <div id="tab-planning" class="hidden space-y-6">
            <!-- Diagramme de Gantt -->
            <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-4">
                <div class="flex justify-between items-center">
                    <h2 class="text-lg font-semibold text-slate-700">📊 Diagramme de Gantt (Planification)</h2>
                    <div class="flex flex-wrap gap-3 text-xs">
                        <span class="flex items-center gap-1"><span class="w-3 h-3 bg-purple-600 rounded inline-block"></span> App Pilote</span>
                        <span class="flex items-center gap-1"><span class="w-3 h-3 bg-indigo-500 rounded inline-block"></span> Ouverte</span>
                        <span class="flex items-center gap-1"><span class="w-3 h-3 bg-blue-500 rounded inline-block"></span> En cours</span>
                        <span class="flex items-center gap-1"><span class="w-3 h-3 bg-emerald-500 rounded inline-block"></span> Résolue</span>
                    </div>
                </div>
                <div class="space-y-1">
                    GANTT_ROWS_PLACEHOLDER
                </div>
            </div>

            <!-- Liste chronologique -->
            <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-4">
                <h2 class="text-lg font-semibold text-slate-700">📅 Liste Chronologique des Échéances</h2>
                <div class="space-y-4">
                    PLANNING_CARDS_PLACEHOLDER
                </div>
            </div>
        </div>

    </div>

    <script>
        function switchTab(tab) {
            const regTab = document.getElementById('tab-register');
            const planTab = document.getElementById('tab-planning');
            const btnReg = document.getElementById('btn-register');
            const btnPlan = document.getElementById('btn-planning');

            if (tab === 'register') {
                regTab.classList.remove('hidden');
                planTab.classList.add('hidden');
                btnReg.className = 'px-4 py-2 rounded font-medium text-sm bg-blue-600 text-white';
                btnPlan.className = 'px-4 py-2 rounded font-medium text-sm bg-white text-slate-600 border';
            } else {
                regTab.classList.add('hidden');
                planTab.classList.remove('hidden');
                btnPlan.className = 'px-4 py-2 rounded font-medium text-sm bg-blue-600 text-white';
                btnReg.className = 'px-4 py-2 rounded font-medium text-sm bg-white text-slate-600 border';
            }
        }

        function updateMinTargetDate() {
            const startDate = document.getElementById('debt_start_date').value;
            const targetDateInput = document.getElementById('debt_target_date');
            if (startDate) {
                targetDateInput.min = startDate;
                if (targetDateInput.value && targetDateInput.value < startDate) {
                    targetDateInput.value = startDate;
                }
            } else {
                targetDateInput.removeAttribute('min');
            }
        }

        function filterTable() {
            const filterValue = document.getElementById('filterPilot').value;
            const rows = document.querySelectorAll('.debt-row');
            
            rows.forEach(row => {
                const isPilot = row.getAttribute('data-pilot') === 'true';
                if (filterValue === 'pilot' && !isPilot) {
                    row.style.display = 'none';
                } else {
                    row.style.display = '';
                }
            });
        }

        function openEditDebt(id, projectId, title, category, impact, costDays, assignee, startDate, targetDate) {
            document.getElementById('debt_id').value = id;
            document.getElementById('debt_project_id').value = projectId;
            document.getElementById('debt_title').value = title;
            document.getElementById('debt_category').value = category;
            document.getElementById('debt_impact').value = impact;
            document.getElementById('debt_cost_days').value = costDays;
            document.getElementById('debt_assignee').value = assignee === 'Non assigné' ? '' : assignee;
            document.getElementById('debt_start_date').value = startDate;
            document.getElementById('debt_target_date').value = targetDate;
            
            updateMinTargetDate();

            document.getElementById('debt-form-title').innerText = "✏️ Modifier la Dette";
            document.getElementById('debt-submit-btn').innerText = "Mettre à jour";
            document.getElementById('debt-cancel-btn').classList.remove('hidden');
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function resetDebtForm() {
            document.getElementById('debt_id').value = '';
            document.getElementById('debt_project_id').value = '';
            document.getElementById('debt_title').value = '';
            document.getElementById('debt_category').value = 'Code';
            document.getElementById('debt_impact').value = 'Moyen';
            document.getElementById('debt_cost_days').value = '';
            document.getElementById('debt_assignee').value = '';
            document.getElementById('debt_start_date').value = '';
            document.getElementById('debt_target_date').value = '';
            document.getElementById('debt_target_date').removeAttribute('min');
            document.getElementById('debtMessage').innerText = '';

            document.getElementById('debt-form-title').innerText = "⚠️ Déclarer une Dette";
            document.getElementById('debt-submit-btn').innerText = "Ajouter la dette";
            document.getElementById('debt-cancel-btn').classList.add('hidden');
        }

        async function createProject(form) {
            const formData = new FormData(form);
            const isPilot = document.getElementById('is_pilot_checkbox').checked;
            const msgEl = document.getElementById('projectMessage');
            
            const res = await fetch(`/api/projects?name=${encodeURIComponent(formData.get('name'))}&description=${encodeURIComponent(formData.get('description'))}&is_pilot=${isPilot}`, {
                method: 'POST'
            });
            
            if (res.ok) {
                window.location.reload();
            } else {
                const err = await res.json();
                msgEl.innerText = err.detail;
                msgEl.className = 'text-xs mt-3 font-medium text-rose-600';
            }
        }

        async function saveDebt(form) {
            const id = document.getElementById('debt_id').value;
            const formData = new FormData(form);
            const startDate = formData.get('start_date');
            const targetDate = formData.get('target_date');
            const msgEl = document.getElementById('debtMessage');

            if (startDate && targetDate && targetDate < startDate) {
                msgEl.innerText = "Erreur : La date cible doit être supérieure ou égale à la date de début.";
                msgEl.className = 'text-xs mt-3 font-medium text-rose-600';
                return;
            }

            const params = new URLSearchParams();
            for (const pair of formData.entries()) {
                if (pair[0] !== 'debt_id') {
                    params.append(pair[0], pair[1]);
                }
            }

            let url = `/api/debts?${params.toString()}`;
            let method = 'POST';

            if (id) {
                url = `/api/debts/${id}?${params.toString()}`;
                method = 'PUT';
            }

            const res = await fetch(url, { method: method });
            if (res.ok) {
                resetDebtForm();
                window.location.reload();
            } else {
                const err = await res.json();
                msgEl.innerText = err.detail || "Erreur lors de l'enregistrement de la dette";
                msgEl.className = 'text-xs mt-3 font-medium text-rose-600';
            }
        }

        async function deleteDebt(id) {
            if (!confirm("Voulez-vous vraiment supprimer cette dette ?")) return;

            const res = await fetch(`/api/debts/${id}`, { method: 'DELETE' });
            if (res.ok) {
                window.location.reload();
            } else {
                alert("Erreur lors de la suppression");
            }
        }

        async function updateStatus(id, newStatus) {
            await fetch(`/api/debts/${id}/status?status=${encodeURIComponent(newStatus)}`, {
                method: 'PATCH'
            });
        }

        async function uploadFile() {
            const fileInput = document.getElementById('fileInput');
            const file = fileInput.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            try {
                const res = await fetch('/api/projects/import', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (res.ok) {
                    document.getElementById('importMessage').innerText = data.message;
                    document.getElementById('importMessage').className = 'text-xs mt-3 font-medium text-emerald-600';
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    document.getElementById('importMessage').innerText = 'Erreur : ' + data.detail;
                    document.getElementById('importMessage').className = 'text-xs mt-3 font-medium text-rose-600';
                }
            } catch (err) {
                document.getElementById('importMessage').innerText = 'Erreur réseau.';
                document.getElementById('importMessage').className = 'text-xs mt-3 font-medium text-rose-600';
            }
        }
    </script>
</body>
</html>"""

    # Injection dynamique sécurisée
    html_content = html_content.replace("DEBTS_COUNT_PLACEHOLDER", str(len(debts)))
    html_content = html_content.replace("TOTAL_COST_PLACEHOLDER", str(total_cost))
    html_content = html_content.replace("PROJECT_OPTIONS_PLACEHOLDER", project_options)
    html_content = html_content.replace("DEBTS_ROWS_PLACEHOLDER", debts_rows)
    html_content = html_content.replace("PLANNING_CARDS_PLACEHOLDER", planning_cards)
    html_content = html_content.replace("GANTT_ROWS_PLACEHOLDER", gantt_rows)

    return html_content