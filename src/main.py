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

# --- API Endpoints : Projets ---

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

# --- API Endpoints : Dettes Techniques (CRUD complet) ---

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

@app.put("/api/debts/{debt_id}")
def update_debt_endpoint(
    debt_id: int,
    project_id: int,
    title: str,
    category: str,
    impact: str,
    cost_days: int,
    assignee: str = "",
    target_date: str = "",
    db: Session = Depends(get_db)
):
    db_debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    
    target = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else None
    db_debt.project_id = project_id
    db_debt.title = title
    db_debt.category = category
    db_debt.impact = impact
    db_debt.cost_days = cost_days
    db_debt.assignee = assignee if assignee else None
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
    
    project_options = "".join([f'<option value="{p.id}">{p.name}</option>' for p in projects])
    
    # Tableau des Dettes avec colonnes Modifier / Supprimer
    debts_rows = ""
    for d in debts:
        p_name = d.project.name if d.project else "Inconnu"
        badge_color = "bg-rose-100 text-rose-700" if d.impact == "Élevé" else ("bg-amber-100 text-amber-700" if d.impact == "Moyen" else "bg-emerald-100 text-emerald-700")
        target_date_str = d.target_date.strftime("%Y-%m-%d") if d.target_date else ""
        
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
            <td class="p-3 text-right space-x-1">
                <button onclick="openEditDebt({d.id}, {d.project_id}, `{d.title}`, `{d.category}`, `{d.impact}`, {d.cost_days}, `{d.assignee or ''}`, `{target_date_str}`)" class="px-2 py-1 bg-amber-50 text-amber-700 rounded text-xs border border-amber-200 hover:bg-amber-100">Modifier</button>
                <button onclick="deleteDebt({d.id})" class="px-2 py-1 bg-rose-50 text-rose-700 rounded text-xs border border-rose-200 hover:bg-rose-100">Supprimer</button>
            </td>
        </tr>
        """
    if not debts:
        debts_rows = '<tr><td colspan="5" class="p-8 text-center text-slate-400">Aucune dette enregistrée pour le moment.</td></tr>'

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
                <!-- Ajouter Application -->
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-4">📂 Ajouter une Application</h2>
                    <form onsubmit="event.preventDefault(); createProject(this);" class="space-y-4">
                        <input name="name" type="text" placeholder="Nom de l'application" class="w-full border p-2 rounded text-sm" required />
                        <textarea name="description" placeholder="Courte description..." class="w-full border p-2 rounded text-sm" rows="2"></textarea>
                        <button type="submit" class="w-full bg-slate-800 text-white py-2 rounded text-sm font-medium hover:bg-slate-700">Enregistrer l'App</button>
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

                        <div>
                            <label class="block text-xs text-slate-500 mb-1">Date cible de résolution :</label>
                            <input name="target_date" id="debt_target_date" type="date" class="w-full border p-2 rounded text-sm" />
                        </div>

                        <div class="flex gap-2">
                            <button type="submit" id="debt-submit-btn" class="flex-1 bg-blue-600 text-white py-2 rounded text-sm font-medium hover:bg-blue-700">Ajouter la dette</button>
                            <button type="button" id="debt-cancel-btn" onclick="resetDebtForm()" class="hidden px-3 bg-slate-200 text-slate-700 rounded text-sm font-medium hover:bg-slate-300">Annuler</button>
                        </div>
                    </form>
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

        function openEditDebt(id, projectId, title, category, impact, costDays, assignee, targetDate) {
            document.getElementById('debt_id').value = id;
            document.getElementById('debt_project_id').value = projectId;
            document.getElementById('debt_title').value = title;
            document.getElementById('debt_category').value = category;
            document.getElementById('debt_impact').value = impact;
            document.getElementById('debt_cost_days').value = costDays;
            document.getElementById('debt_assignee').value = assignee === 'Non assigné' ? '' : assignee;
            document.getElementById('debt_target_date').value = targetDate;

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
            document.getElementById('debt_target_date').value = '';

            document.getElementById('debt-form-title').innerText = "⚠️ Déclarer une Dette";
            document.getElementById('debt-submit-btn').innerText = "Ajouter la dette";
            document.getElementById('debt-cancel-btn').classList.add('hidden');
        }

        async function createProject(form) {
            const formData = new FormData(form);
            const res = await fetch(`/api/projects?name=${encodeURIComponent(formData.get('name'))}&description=${encodeURIComponent(formData.get('description'))}`, {
                method: 'POST'
            });
            if (res.ok) {
                window.location.reload();
            } else {
                const err = await res.json();
                alert("Erreur : " + err.detail);
            }
        }

        async function saveDebt(form) {
            const id = document.getElementById('debt_id').value;
            const formData = new FormData(form);
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
                alert("Erreur lors de l'enregistrement de la dette");
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
    html_content = html_content.replace("DEBTS_ROWS_PLACEHOLDER", debts_rows)
    html_content = html_content.replace("PLANNING_CARDS_PLACEHOLDER", planning_cards)

    return html_content