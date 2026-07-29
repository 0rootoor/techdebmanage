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

# --- API Endpoints : Projets & Import ---

@app.post("/api/projects")
def create_project_endpoint(name: str, description: str, db: Session = Depends(get_db)):
    db_project = ProjectModel(name=name, description=description)
    db.add(db_project)
    db.commit()
    return {"message": "Projet créé"}

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

# --- Interface Frontend ---

@app.get("/", response_class=HTMLResponse)
def read_root(db: Session = Depends(get_db)):
    projects = db.query(ProjectModel).all()
    debts = db.query(TechDebtModel).all()
    total_cost = sum(d.cost_days for d in debts)
    
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
                <span class="px-2 py-1 rounded text-xs font-medium bg-slate-100 text-slate-700">{d.status}</span>
            </td>
        </tr>
        """
    
    if not debts:
        debts_rows = '<tr><td colspan="4" class="p-8 text-center text-slate-400">Aucune dette enregistrée pour le moment.</td></tr>'

    html_content = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Gestionnaire Pro & Dette Technique</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 min-h-screen p-6">
    <div class="max-w-6xl mx-auto space-y-8">
        
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

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="space-y-6">
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-4">📂 Ajouter une Application</h2>
                    <form onsubmit="event.preventDefault(); createProject(this);" class="space-y-4">
                        <input name="name" type="text" placeholder="Nom de l'application" class="w-full border p-2 rounded text-sm" required />
                        <textarea name="description" placeholder="Courte description..." class="w-full border p-2 rounded text-sm" rows="2"></textarea>
                        <button type="submit" class="w-full bg-slate-800 text-white py-2 rounded text-sm font-medium hover:bg-slate-700">Enregistrer l'App</button>
                    </form>
                </div>

                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-2">📊 Importer depuis Excel / CSV</h2>
                    <p class="text-xs text-slate-500 mb-4">Le fichier doit contenir une colonne <code class="bg-slate-100 p-0.5 rounded font-bold">name</code>.</p>
                    <form onsubmit="event.preventDefault(); uploadFile();" class="space-y-4">
                        <input type="file" id="fileInput" accept=".xlsx, .xls, .csv" class="w-full text-sm border p-2 rounded file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700" required />
                        <button type="submit" class="w-full bg-emerald-600 text-white py-2 rounded text-sm font-medium hover:bg-emerald-700">Lancer l'import</button>
                    </form>
                    <p id="importMessage" class="text-xs mt-3 font-medium text-emerald-600"></p>
                </div>
            </div>

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
    </div>

    <script>
        async function createProject(form) {
            const formData = new FormData(form);
            const name = formData.get('name');
            const description = formData.get('description');
            
            const res = await fetch(`/api/projects?name=${encodeURIComponent(name)}&description=${encodeURIComponent(description)}`, {
                method: 'POST'
            });
            if (res.ok) {
                window.location.reload();
            } else {
                alert("Erreur lors de la création du projet");
            }
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

    # Injection sécurisée des données Python dans le HTML
    html_content = html_content.replace("DEBTS_COUNT_PLACEHOLDER", str(len(debts)))
    html_content = html_content.replace("TOTAL_COST_PLACEHOLDER", str(total_cost))
    html_content = html_content.replace("DEBTS_ROWS_PLACEHOLDER", debts_rows)

    return html_content