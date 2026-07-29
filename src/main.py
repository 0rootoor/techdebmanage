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

# --- Schémas Pydantic ---

class ProjectCreate(BaseModel):
    name: str
    description: str

class ProjectResponse(ProjectCreate):
    id: int
    class Config:
        from_attributes = True

class TechDebtCreate(BaseModel):
    title: str
    category: str = "Code"
    impact: str = "Moyen"
    cost_days: int
    target_date: str | None = None
    assignee: str | None = None
    project_id: int

class TechDebtResponse(BaseModel):
    id: int
    title: str
    category: str
    impact: str
    cost_days: int
    status: str
    created_at: str
    target_date: str | None
    assignee: str | None
    project_id: int
    project_name: str

    class Config:
        from_attributes = True

# --- Application FastAPI ---

app = FastAPI(title="Gestion Avancée de la Dette Technique")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API Endpoints : Projets ---

@app.post("/api/projects", response_model=ProjectResponse)
def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    db_project = ProjectModel(name=project.name, description=project.description)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@app.get("/api/projects", response_model=list[ProjectResponse])
def get_projects(db: Session = Depends(get_db)):
    return db.query(ProjectModel).all()

# --- Endpoint d'Import Excel / CSV ---

@app.post("/api/projects/import")
async def import_projects(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Format de fichier non supporté. Utilisez .csv ou .xlsx")

        if 'name' not in df.columns:
            raise HTTPException(status_code=400, detail="Le fichier doit contenir au moins une colonne nommée 'name'")

        imported_count = 0
        for _, row in df.iterrows():
            name = str(row['name']).strip()
            if not name or name == 'nan':
                continue
            
            description = str(row.get('description', 'Importé depuis Excel')).strip()
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
        raise HTTPException(status_code=400, detail=f"Erreur lors du traitement du fichier : {str(e)}")

# --- API Endpoints : Dettes Techniques ---

@app.post("/api/debts", response_model=TechDebtResponse)
def create_debt(debt: TechDebtCreate, db: Session = Depends(get_db)):
    target = datetime.strptime(debt.target_date, "%Y-%m-%d").date() if debt.target_date else None
    db_debt = TechDebtModel(
        title=debt.title,
        category=debt.category,
        impact=debt.impact,
        cost_days=debt.cost_days,
        target_date=target,
        assignee=debt.assignee,
        project_id=debt.project_id
    )
    db.add(db_debt)
    db.commit()
    db.refresh(db_debt)
    
    return TechDebtResponse(
        id=db_debt.id,
        title=db_debt.title,
        category=db_debt.category,
        impact=db_debt.impact,
        cost_days=db_debt.cost_days,
        status=db_debt.status,
        created_at=db_debt.created_at.strftime("%Y-%m-%d"),
        target_date=db_debt.target_date.strftime("%Y-%m-%d") if db_debt.target_date else None,
        assignee=db_debt.assignee,
        project_id=db_debt.project_id,
        project_name=db_debt.project.name
    )

@app.put("/api/debts/{debt_id}", response_model=TechDebtResponse)
def update_debt(debt_id: int, debt: TechDebtCreate, db: Session = Depends(get_db)):
    db_debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    
    db_debt.title = debt.title
    db_debt.category = debt.category
    db_debt.impact = debt.impact
    db_debt.cost_days = debt.cost_days
    db_debt.target_date = datetime.strptime(debt.target_date, "%Y-%m-%d").date() if debt.target_date else None
    db_debt.assignee = debt.assignee
    db_debt.project_id = debt.project_id
    
    db.commit()
    db.refresh(db_debt)
    
    return TechDebtResponse(
        id=db_debt.id,
        title=db_debt.title,
        category=db_debt.category,
        impact=db_debt.impact,
        cost_days=db_debt.cost_days,
        status=db_debt.status,
        created_at=db_debt.created_at.strftime("%Y-%m-%d"),
        target_date=db_debt.target_date.strftime("%Y-%m-%d") if db_debt.target_date else None,
        assignee=db_debt.assignee,
        project_id=db_debt.project_id,
        project_name=db_debt.project.name if db_debt.project else "Inconnu"
    )

@app.get("/api/debts", response_model=list[TechDebtResponse])
def get_debts(db: Session = Depends(get_db)):
    debts = db.query(TechDebtModel).all()
    result = []
    for d in debts:
        result.append(TechDebtResponse(
            id=d.id,
            title=d.title,
            category=d.category,
            impact=d.impact,
            cost_days=d.cost_days,
            status=d.status,
            created_at=d.created_at.strftime("%Y-%m-%d"),
            target_date=d.target_date.strftime("%Y-%m-%d") if d.target_date else None,
            assignee=d.assignee,
            project_id=d.project_id,
            project_name=d.project.name if d.project else "Inconnu"
        ))
    return result

@app.patch("/api/debts/{debt_id}/status")
def update_debt_status(debt_id: int, status: str, db: Session = Depends(get_db)):
    db_debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    db_debt.status = status
    db.commit()
    return {"message": "Statut mis à jour avec succès"}

# --- Interface Frontend ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Gestionnaire Pro & Dette Technique</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
</head>
<body class="bg-slate-100 min-h-screen p-6">
    <div id="app" class="max-w-6xl mx-auto space-y-8">
        
        <header class="flex justify-between items-center bg-white p-6 rounded-xl shadow-sm border border-slate-200">
            <div>
                <h1 class="text-2xl font-bold text-slate-800">🚀 TechDebt Manager Pro</h1>
                <p class="text-sm text-slate-500">Suivi des applications, projets, planification et import Excel</p>
            </div>
            <div class="flex gap-4">
                <div class="text-right">
                    <p class="text-xs text-slate-400">Total Dettes</p>
                    <p class="text-xl font-bold text-blue-600">{{ debts.length }}</p>
                </div>
                <div class="text-right border-l pl-4">
                    <p class="text-xs text-slate-400">Charge Totale</p>
                    <p class="text-xl font-bold text-amber-600">{{ totalCost }} jours</p>
                </div>
            </div>
        </header>

        <div class="flex gap-2 border-b pb-2">
            <button @click="currentTab = 'register'" :class="{'px-4 py-2 rounded font-medium text-sm': true, 'bg-blue-600 text-white': currentTab === 'register', 'bg-white text-slate-600 border': currentTab !== 'register'}">Registre & Saisie</button>
            <button @click="currentTab = 'planning'" :class="{'px-4 py-2 rounded font-medium text-sm': true, 'bg-blue-600 text-white': currentTab === 'planning', 'bg-white text-slate-600 border': currentTab !== 'planning'}">📅 Planning & Échéances</button>
        </div>

        <div v-if="currentTab === 'register'" class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="space-y-6">
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-4">📂 Ajouter une Application</h2>
                    <form @submit.prevent="submitProject" class="space-y-4">
                        <input v-model="projectForm.name" type="text" placeholder="Nom de l'application" class="w-full border p-2 rounded text-sm" required />
                        <textarea v-model="projectForm.description" placeholder="Courte description..." class="w-full border p-2 rounded text-sm" rows="2"></textarea>
                        <button type="submit" class="w-full bg-slate-800 text-white py-2 rounded text-sm font-medium hover:bg-slate-700">Enregistrer l'App</button>
                    </form>
                </div>

                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-2">📊 Importer depuis Excel / CSV</h2>
                    <p class="text-xs text-slate-500 mb-4">Le fichier doit contenir au moins une colonne <code class="bg-slate-100 p-0.5 rounded font-bold">name</code>.</p>
                    <form @submit.prevent="submitImport" class="space-y-4">
                        <input type="file" ref="fileInput" accept=".xlsx, .xls, .csv" class="w-full text-sm border p-2 rounded file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700" required />
                        <button type="submit" class="w-full bg-emerald-600 text-white py-2 rounded text-sm font-medium hover:bg-emerald-700">Lancer l'import</button>
                    </form>
                    <p v-if="importMessage" class="text-xs mt-3 font-medium text-emerald-600">{{ importMessage }}</p>
                </div>

                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="text-lg font-semibold text-slate-700 mb-4">{{ isEditing ? '✏️ Modifier la Dette' : '⚠️ Déclarer une Dette' }}</h2>
                    <form @submit.prevent="submitDebt" class="space-y-4">
                        <select v-model="debtForm.project_id" class="w-full border p-2 rounded text-sm" required>
                            <option disabled value="">Sélectionner une application</option>
                            <option v-for="p in projects" :value="p.id">{{ p.name }}</option>
                        </select>
                        <input v-model="debtForm.title" type="text" placeholder="Intitulé de la dette" class="w-full border p-2 rounded text-sm" required />
                        
                        <div class="grid grid-cols-2 gap-2">
                            <select v-model="debtForm.category" class="border p-2 rounded text-sm">
                                <option value="Code">Code Legacy</option>
                                <option value="Architecture">Architecture</option>
                                <option value="Sécurité">Sécurité</option>
                                <option value="Documentation">Documentation</option>
                                <option value="Tests">Manque de tests</option>
                            </select>
                            <select v-model="debtForm.impact" class="border p-2 rounded text-sm">
                                <option value="Faible">Impact Faible</option>
                                <option value="Moyen">Impact Moyen</option>
                                <option value="Élevé">Impact Élevé</option>
                            </select>
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <input v-model.number="debtForm.cost_days" type="number" placeholder="Coût (jours)" class="border p-2 rounded text-sm" required />
                            <input v-model="debtForm.assignee" type="text" placeholder="Responsable" class="border p-2 rounded text-sm" />
                        </div>

                        <div>
                            <label class="block text-xs text-slate-500 mb-1">Date cible de résolution :</label>
                            <input v-model="debtForm.target_date" type="date" class="w-full border p-2 rounded text-sm" />
                        </div>

                        <div class="flex gap-2">
                            <button type="submit" class="flex-1 bg-blue-600 text-white py-2 rounded text-sm font-medium hover:bg-blue-700">
                                {{ isEditing ? 'Mettre à jour' : 'Ajouter la dette' }}
                            </button>
                            <button v-if="isEditing" @click="cancelEdit" type="button" class="bg-gray-300 text-slate-700 px-3 py-2 rounded text-sm">Annuler</button>
                        </div>
                    </form>
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
                                    <th class="p-3">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="debt in debts" :key="debt.id" class="border-b hover:bg-slate-50">
                                    <td class="p-3">
                                        <div class="font-semibold text-slate-800">{{ debt.title }}</div>
                                        <div class="text-xs text-blue-600 font-medium">📦 {{ debt.project_name }}</div>
                                    </td>
                                    <td class="p-3">
                                        <span class="inline-block px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-700 mr-1">{{ debt.category }}</span>
                                        <span :class="{
                                            'px-2 py-0.5 rounded text-xs font-semibold': true,
                                            'bg-rose-100 text-rose-700': debt.impact === 'Élevé',
                                            'bg-amber-100 text-amber-700': debt.impact === 'Moyen',
                                            'bg-emerald-100 text-emerald-700': debt.impact === 'Faible'
                                        }">{{ debt.impact }}</span>
                                    </td>
                                    <td class="p-3 text-xs text-slate-600">
                                        <div class="font-medium text-slate-800">{{ debt.cost_days }} jours</div>
                                        <div v-if="debt.assignee" class="text-indigo-600">👤 {{ debt.assignee }}</div>
                                    </td>
                                    <td class="p-3">
                                        <select v-model="debt.status" @change="updateStatus(debt.id, debt.status)" class="border rounded p-1 text-xs bg-white">
                                            <option value="Ouverte">Ouverte</option>
                                            <option value="En cours">En cours</option>
                                            <option value="Résolue">Résolue</option>
                                        </select>
                                    </td>
                                    <td class="p-3">
                                        <button @click="startEdit(debt)" class="text-blue-600 hover:underline text-xs font-medium">Modifier</button>
                                    </td>
                                </tr>
                                <tr v-if="debts.length === 0">
                                    <td colspan="5" class="p-8 text-center text-slate-400">Aucune dette enregistrée pour le moment.</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <div v-if="currentTab === 'planning'" class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-6">
            <h2 class="text-lg font-semibold text-slate-700">📅 Planning de Résolution (Trié par Date Cible)</h2>
            <div class="space-y-4">
                <div v-for="debt in sortedDebtsByDate" :key="debt.id" class="p-4 border rounded-lg flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-slate-50">
                    <div class="space-y-1">
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-bold px-2 py-0.5 bg-blue-100 text-blue-700 rounded">{{ debt.project_name }}</span>
                            <span class="text-sm font-bold text-slate-800">{{ debt.title }}</span>
                        </div>
                        <div class="text-xs text-slate-500 flex gap-4">
                            <span>Charge : <strong>{{ debt.cost_days }}j</strong></span>
                            <span>Responsable : <strong class="text-indigo-600">{{ debt.assignee || 'Non assigné' }}</strong></span>
                            <span>Statut : <strong>{{ debt.status }}</strong></span>
                        </div>
                    </div>
                    <div class="text-right">
                        <div class="text-xs text-slate-400">Échéance cible</div>
                        <div class="text-sm font-bold text-rose-600">{{ debt.target_date || 'Non planifiée' }}</div>
                    </div>
                </div>
                <div v-if="debts.length === 0" class="text-center text-slate-400 py-6">Aucune dette à planifier.</div>
            </div>
        </div>

    </div>

    <script>
        const { createApp, ref, computed, onMounted } = Vue;
        createApp({
            setup() {
                const currentTab = ref('register');
                const projects = ref([]);
                const debts = ref([]);
                const isEditing = ref(false);
                const editingId = ref(null);
                const importMessage = ref('');
                const fileInput = ref(null);

                const projectForm = ref({ name: '', description: '' });
                const debtForm = ref({ title: '', category: 'Code', impact: 'Moyen', cost_days: '', target_date: '', assignee: '', project_id: '' });

                const fetchData = async () => {
                    const resP = await fetch('/api/projects');
                    projects.value = await resP.json();

                    const resD = await fetch('/api/debts');
                    debts.value = await resD.json();
                };

                const submitProject = async () => {
                    if (!projectForm.value.name) return;
                    await fetch('/api/projects', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(projectForm.value)
                    });
                    projectForm.value.name = '';
                    projectForm.value.description = '';
                    fetchData();
                };

                const submitImport = async () => {
                    const file = fileInput.value.files[0];
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
                            importMessage.value = data.message;
                            fetchData();
                            fileInput.value.value = '';
                        } else {
                            importMessage.value = 'Erreur : ' + data.detail;
                        }
                    } catch (err) {
                        importMessage.value = 'Erreur réseau lors de l\'importation.';
                    }
                };

                const submitDebt = async () => {
                    if (!debtForm.value.title || !debtForm.value.project_id) return;

                    const url = isEditing.value ? `/api/debts/${editingId.value}` : '/api/debts';
                    const method = isEditing.value ? 'PUT' : 'POST';

                    await fetch(url, {
                        method: method,
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(debtForm.value)
                    });

                    cancelEdit();
                    fetchData();
                };

                const startEdit = (debt) => {
                    isEditing.value = true;
                    editingId.value = debt.id;
                    debtForm.value = {
                        title: debt.title,
                        category: debt.category,
                        impact: debt.impact,
                        cost_days: debt.cost_days,
                        target_date: debt.target_date || '',
                        assignee: debt.assignee || '',
                        project_id: debt.project_id
                    };
                    currentTab.value = 'register';
                };

                const cancelEdit = () => {
                    isEditing.value = false;
                    editingId.value = null;
                    debtForm.value = { title: '', category: 'Code', impact: 'Moyen', cost_days: '', target_date: '', assignee: '', project_id: '' };
                };

                const updateStatus = async (id, newStatus) => {
                    await fetch(`/api/debts/${id}/status?status=${encodeURIComponent(newStatus)}`, {
                        method: 'PATCH'
                    });
                };

                const totalCost = computed(() => {
                    return debts.value.reduce((acc, curr) => acc + curr.cost_days, 0);
                });

                const sortedDebtsByDate = computed(() => {
                    return [...debts.value].sort((a, b) => {
                        if (!a.target_date) return 1;
                        if (!b.target_date) return -1;
                        return a.target_date.localeCompare(b.target_date);
                    });
                });

                onMounted(fetchData);

                return { 
                    currentTab, projects, debts, projectForm, debtForm, 
                    isEditing, submitProject, submitImport, submitDebt, startEdit, cancelEdit, 
                    updateStatus, totalCost, sortedDebtsByDate, importMessage, fileInput 
                };
            }
        }).mount('#app');
    </script>
</body>
</html>
    """