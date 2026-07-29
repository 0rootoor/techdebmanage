from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import date, datetime
import pandas as pd
import io

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

# --- API Endpoints : Projets & Gestion ---

@app.post("/api/projects")
def create_project_endpoint(name: str, description: str = "", db: Session = Depends(get_db)):
    if not name.strip():
        raise HTTPException(status_code=400, detail="Le nom du projet est requis")
    existing = db.query(ProjectModel).filter(ProjectModel.name == name.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ce projet existe déjà")
    
    db_project = ProjectModel(name=name.strip(), description=description.strip())
    db.add(db_project)
    db.commit()
    return {"message": "Projet créé avec succès"}

@app.put("/api/projects/{project_id}")
def update_project_endpoint(project_id: int, name: str, description: str = "", db: Session = Depends(get_db)):
    db_project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="Application non trouvée")
    
    if not name.strip():
        raise HTTPException(status_code=400, detail="Le nom du projet est requis")
    
    existing = db.query(ProjectModel).filter(ProjectModel.name == name.strip(), ProjectModel.id != project_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Une autre application porte déjà ce nom")

    db_project.name = name.strip()
    db_project.description = description.strip()
    db.commit()
    return {"message": "Application mise à jour avec succès"}

@app.delete("/api/projects/{project_id}")
def delete_project_endpoint(project_id: int, db: Session = Depends(get_db)):
    db_project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="Application non trouvée")
    db.delete(db_project)
    db.commit()
    return {"message": "Application supprimée avec succès"}

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
            if not name or name == 'nan':
                continue
            description = str(row.get('description', '')).strip()
            if description == 'nan':
                description = ''

            existing = db.query(ProjectModel).filter(ProjectModel.name == name).first()
            if not existing:
                db_project = ProjectModel(name=name, description=description)
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
    target_date: str = "",
    db: Session = Depends(get_db)
):
    target = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else None
    db_debt = TechDebtModel(
        title=title,
        category=category,
        impact=impact,
        cost_days=cost_days,
        assignee=assignee if assignee else None,
        target_date=target,
        project_id=project_id
    )
    db.add(db_debt)
    db.commit()
    return {"message": "Dette ajoutée avec succès"}

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
    
    project_options = "".join([f'<option value="{p.id}">{p.name}</option>' for p in projects])
    
    # Tableau des Applications (au centre)
    projects_rows = ""
    for p in projects:
        p_desc = p.description or "Aucune description"
        projects_rows += f"""
        <tr class="border-b hover:bg-slate-50">
            <td class="p-3 font-semibold text-slate-800">{p.name}</td>
            <td class="p-3 text-xs text-slate-500">{p_desc}</td>
            <td class="p-3 text-right space-x-1">
                <button onclick="openEditProject({p.id}, '{p.name}', `{p_desc}`)" class="px-2 py-1 bg-amber-50 text-amber-700 rounded text-xs border border-amber-200 hover:bg-amber-100">Modifier</button>
                <button onclick="deleteProject({p.id})" class="px-2 py-1 bg-rose-50 text-rose-700 rounded text-xs border border-rose-200 hover:bg-rose-100">Supprimer</button>
            </td>
        </tr>
        """
    if not projects:
        projects_rows = '<tr><td colspan="3" class="p-6 text-center text-slate-400">Aucune application enregistrée.</td></tr>'

    # Tableau des Dettes (au centre)
    debts_rows = ""
    for d in debts:
        p_name = d.project.name if d.project else "Inconnu"
        badge_color = "bg-rose-100 text-rose-700" if d.impact == "Élevé" else ("bg-amber-100 text-amber-700" if d.impact == "Moyen" else "bg-emerald-100 text-emerald-700")
        debts_rows += f"""
        <tr class="border-b hover:bg-slate-50">
            <td class="p-3">
                <div class="font-semibold text-slate-800">{d.title}</div>
                <div class="text-xs text-blue-600 font-medium">📦 {p_name}</div>
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
        </tr>
        """
    if not debts:
        debts_rows = '<tr><td colspan="4" class="p-8 text-center text-slate-400">Aucune dette enregistrée pour le moment.</td></tr>'

    # Planning
    sorted_debts = sorted(debts, key=lambda x: x.target_date if x.target_date else date.max)
    planning_cards = ""
    for d in sorted_debts:
        p_name = d.project.name if d.project else "Inconnu"
        target_str = d.target_date.strftime("%Y-%m-%d") if d.target_date else "Non planifiée"
        planning_cards += f"""
        <div class="p-4 border rounded-lg flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-slate-50">
            <div class="space-y-1">
                <div class="flex items-center gap-2">
                    <span class="text-xs font-bold px-2 py-0.5 bg-blue-100 text-blue-700 rounded">{p_name}</span>
                    <span class="text-sm font-bold text-slate-800">{d.title}</span>
                </div>
                <div class="text-xs text-slate-500 flex gap-4">
                    <span>Charge : <strong>{d.cost_days}j</strong></span>
                    <span>Responsable : <strong class="text-indigo-600">{d.assignee or 'Non assigné'}</strong></span>
                    <span>Statut : <strong>{d.status}</strong></span>
                </div>
            </div>
            <div class="text-right">
                <div class="text-xs text-slate-400">Échéance cible</div>
                <div class="text-sm font-bold text-rose-600">{target_str}</div>
            </div>
        </div>
        """
    if not debts:
        planning_cards = '<div class="text-center text-slate-400 py-6">Aucune dette à planifier.</div>'

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
            <div class="flex gap-4">
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

        <!-- Navigation par onglets -->
        <div class="flex gap-2 border-b pb-2">
            <button onclick="switchTab('register')" id="btn-register" class="px-4 py-2 rounded font-medium text-sm bg-blue-600 text-white">Registre & Saisie</button>
            <button onclick="switchTab('planning')" id="btn-planning" class="px-4 py-2 rounded font-medium text-sm bg-white text-slate-600 border">📅 Planning & Échéances</button>
        </div>

        <!-- ONGLET 1 : REGISTRE ET SAISIE -->
        <div id="tab-register" class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="space-y-6">
                <!-- Formulaire Ajouter/Modifier Application -->
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 id="project-form-title" class="text-lg font-semibold text-slate-700 mb-4">📂 Ajouter une Application</h2>
                    <form onsubmit="event.preventDefault(); saveProject(this);" class="space-y-4">
                        <input type="hidden" id="project_id" name="project_id" value="" />
                        <input name="name" id="project_name" type="text" placeholder="Nom de l'application" class="w-full border p-2 rounded text-sm" required />
                        <textarea name="description" id="project_desc" placeholder="Courte description..." class="w-full border p-2 rounded text-sm" rows="2"></textarea>
                        <div class="flex gap-2">
                            <button type="submit" id="project-submit-btn" class="flex-1 bg-slate-800 text-white py-2 rounded text-sm font-medium hover:bg-slate-700">Enregistrer</button>
                            <button type="button" id="project-cancel-btn" onclick="resetProjectForm()" class="hidden px-3 bg-slate-200 text-slate-700 rounded text-sm font-medium hover:bg-slate-300">Annuler</button>
                        </div>
                    </form>
                </div>

                <!-- Import Excel / CSV -->
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-2">📊 Importer depuis Excel / CSV</h2>
                    <p class="text-xs text-slate-500 mb-4">Le fichier doit contenir une colonne <code class="bg-slate-100 p-0.5 rounded font-bold">name</code>.</p>
                    <form onsubmit="event.preventDefault(); uploadFile();" class="space-y-4">
                        <input type="file" id="fileInput" accept=".xlsx, .xls, .csv" class="w-full text-sm border p-2 rounded file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700" required />
                        <button type="submit" class="w-full bg-emerald-600 text-white py-2 rounded text-sm font-medium hover:bg-emerald-700">Lancer l'import</button>
                    </form>
                    <p id="importMessage" class="text-xs mt-3 font-medium text-emerald-600"></p>
                </div>

                <!-- Déclarer une Dette -->
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-4">⚠️ Déclarer une Dette</h2>
                    <form onsubmit="event.preventDefault(); createDebt(this);" class="space-y-4">
                        <select name="project_id" class="w-full border p-2 rounded text-sm" required>
                            <option disabled selected value="">Sélectionner une application</option>
                            PROJECT_OPTIONS_PLACEHOLDER
                        </select>
                        <input name="title" type="text" placeholder="Intitulé de la dette" class="w-full border p-2 rounded text-sm" required />
                        
                        <div class="grid grid-cols-2 gap-2">
                            <select name="category" class="border p-2 rounded text-sm">
                                <option value="Code">Code Legacy</option>
                                <option value="Architecture">Architecture</option>
                                <option value="Sécurité">Sécurité</option>
                                <option value="Documentation">Documentation</option>
                                <option value="Tests">Manque de tests</option>
                            </select>
                            <select name="impact" class="border p-2 rounded text-sm">
                                <option value="Faible">Impact Faible</option>
                                <option value="Moyen" selected>Impact Moyen</option>
                                <option value="Élevé">Impact Élevé</option>
                            </select>
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <input name="cost_days" type="number" placeholder="Coût (jours)" class="border p-2 rounded text-sm" required />
                            <input name="assignee" type="text" placeholder="Responsable" class="border p-2 rounded text-sm" />
                        </div>

                        <div>
                            <label class="block text-xs text-slate-500 mb-1">Date cible de résolution :</label>
                            <input name="target_date" type="date" class="w-full border p-2 rounded text-sm" />
                        </div>

                        <button type="submit" class="w-full bg-blue-600 text-white py-2 rounded text-sm font-medium hover:bg-blue-700">Ajouter la dette</button>
                    </form>
                </div>
            </div>

            <!-- Colonne Centrale : Registres (Applications & Dettes) -->
            <div class="lg:col-span-2 space-y-6">
                <!-- Registre des Applications -->
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-4">📂 Registre des Applications</h2>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-sm">
                            <thead>
                                <tr class="bg-slate-50 border-b text-slate-500">
                                    <th class="p-3">Nom</th>
                                    <th class="p-3">Description</th>
                                    <th class="p-3 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                PROJECTS_ROWS_PLACEHOLDER
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Registre des Dettes -->
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
                                </tr>
                            </thead>
                            <tbody>
                                DEBTS_ROWS_PLACEHOLDER
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- ONGLET 2 : PLANNING -->
        <div id="tab-planning" class="hidden bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-6">
            <h2 class="text-lg font-semibold text-slate-700">📅 Planning de Résolution (Trié par Date Cible)</h2>
            <p class="text-sm text-slate-500">Vue chronologique des actions de refactoring planifiées.</p>
            <div class="space-y-4">
                PLANNING_CARDS_PLACEHOLDER
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

        function openEditProject(id, name, desc) {
            document.getElementById('project_id').value = id;
            document.getElementById('project_name').value = name;
            document.getElementById('project_desc').value = desc === 'Aucune description' ? '' : desc;
            document.getElementById('project-form-title').innerText = "✏️ Modifier l'Application";
            document.getElementById('project-submit-btn').innerText = "Mettre à jour";
            document.getElementById('project-cancel-btn').classList.remove('hidden');
        }

        function resetProjectForm() {
            document.getElementById('project_id').value = '';
            document.getElementById('project_name').value = '';
            document.getElementById('project_desc').value = '';
            document.getElementById('project-form-title').innerText = "📂 Ajouter une Application";
            document.getElementById('project-submit-btn').innerText = "Enregistrer";
            document.getElementById('project-cancel-btn').classList.add('hidden');
        }

        async function saveProject(form) {
            const id = document.getElementById('project_id').value;
            const name = document.getElementById('project_name').value;
            const description = document.getElementById('project_desc').value;

            let url = `/api/projects?name=${encodeURIComponent(name)}&description=${encodeURIComponent(description)}`;
            let method = 'POST';

            if (id) {
                url = `/api/projects/${id}?name=${encodeURIComponent(name)}&description=${encodeURIComponent(description)}`;
                method = 'PUT';
            }

            const res = await fetch(url, { method: method });
            if (res.ok) {
                window.location.reload();
            } else {
                const err = await res.json();
                alert("Erreur : " + err.detail);
            }
        }

        async function deleteProject(id) {
            if (!confirm("Voulez-vous vraiment supprimer cette application ? (Attention : cela supprimera aussi toutes les dettes associées)")) return;

            const res = await fetch(`/api/projects/${id}`, { method: 'DELETE' });
            if (res.ok) {
                window.location.reload();
            } else {
                const err = await res.json();
                alert("Erreur : " + err.detail);
            }
        }

        async function createDebt(form) {
            const formData = new FormData(form);
            const params = new URLSearchParams();
            for (const pair of formData.entries()) {
                params.append(pair[0], pair[1]);
            }

            const res = await fetch(`/api/debts?${params.toString()}`, {
                method: 'POST'
            });
            if (res.ok) {
                window.location.reload();
            } else {
                alert("Erreur lors de l'ajout de la dette");
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
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    document.getElementById('importMessage').innerText = 'Erreur : ' + data.detail;
                    document.getElementById('importMessage').className = 'text-xs mt-3 font-medium text-rose-600';
                }
            } catch (err) {
                document.getElementById('importMessage').innerText = 'Erreur réseau.';
            }
        }
    </script>
</body>
</html>"""

    # Injection dynamique sécurisée
    html_content = html_content.replace("DEBTS_COUNT_PLACEHOLDER", str(len(debts)))
    html_content = html_content.replace("TOTAL_COST_PLACEHOLDER", str(total_cost))
    html_content = html_content.replace("PROJECT_OPTIONS_PLACEHOLDER", project_options)
    html_content = html_content.replace("PROJECTS_ROWS_PLACEHOLDER", projects_rows)
    html_content = html_content.replace("DEBTS_ROWS_PLACEHOLDER", debts_rows)
    html_content = html_content.replace("PLANNING_CARDS_PLACEHOLDER", planning_cards)

    return html_content