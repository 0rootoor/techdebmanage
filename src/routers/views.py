import os
import json
import inspect
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import ProjectModel, TechDebtModel, AuditLogModel, UserModel, MilestoneModel
from auth import verify_password, hash_password, require_api_auth, ROLE_LABELS, ROLES

router = APIRouter(tags=["views"])

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False).replace("</", "<\\/")

# Détection de la signature de TemplateResponse pour assurer la compatibilité
# entre les anciennes et nouvelles versions de Starlette/FastAPI.
_sig = inspect.signature(templates.TemplateResponse)
if "request" in _sig.parameters:
    # Version moderne (Starlette >= 0.28.0)
    def render_template(request: Request, name: str, context: dict = None, status_code: int = 200):
        context = context or {}
        return templates.TemplateResponse(request=request, name=name, context=context, status_code=status_code)
else:
    # Ancienne version (Starlette < 0.28.0)
    def render_template(request: Request, name: str, context: dict = None, status_code: int = 200):
        context = context or {}
        context["request"] = request
        return templates.TemplateResponse(name, context, status_code=status_code)

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse(url="/", status_code=303)
    return render_template(request, "login.html", {"error": None})

@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.username == username.strip()).first()
    if user and verify_password(password, user.password_hash):
        request.session["authenticated"] = True
        request.session["username"] = user.username
        request.session["role"] = user.role
        request.session["user_id"] = user.id
        return RedirectResponse(url="/", status_code=303)
    return render_template(
        request,
        "login.html",
        {"error": "Identifiant ou mot de passe incorrect."},
        status_code=401,
    )

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@router.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    if not request.session.get("authenticated") or "role" not in request.session:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)
    current_user = request.session.get("username", "Utilisateur")
    current_role = request.session.get("role", "lecture_seule")

    projects = db.query(ProjectModel).order_by(ProjectModel.is_pilot.desc(), ProjectModel.name).all()
    debts = db.query(TechDebtModel).all()
    total_cost = sum(d.cost_days for d in debts)
    sorted_debts = sorted(debts, key=lambda x: x.target_date if x.target_date else date.max)

    open_debts = [d for d in debts if d.status != "Résolue"]
    overdue_debts = [d for d in open_debts if d.target_date and d.target_date < date.today()]
    pilot_projects = [p for p in projects if p.is_pilot]

    distinct_socles = sorted({p.socle for p in projects if p.socle})
    distinct_frameworks = sorted({p.framework for p in projects if p.framework})

    # Agrégats pour les graphiques
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

    from collections import Counter
    socle_counter = Counter(p.socle for p in projects if p.socle)
    socle_labels = sorted(socle_counter, key=lambda k: -socle_counter[k])
    socle_counts = [socle_counter[k] for k in socle_labels]

    framework_counter = Counter(p.framework for p in projects if p.framework)
    framework_labels = sorted(framework_counter, key=lambda k: -framework_counter[k])
    framework_counts = [framework_counter[k] for k in framework_labels]

    app_status_order = ["En projet", "En développement", "En production", "En maintenance", "Décommissionnée"]
    app_status_labels, app_status_counts = [], []
    for s in app_status_order:
        count = sum(1 for p in projects if p.app_status == s)
        if count > 0:
            app_status_labels.append(s)
            app_status_counts.append(count)

    chart_data = {
        "categoryLabels": category_labels,
        "categoryCounts": category_counts,
        "costByCategory": cost_by_category,
        "impactLabels": impact_order,
        "impactCounts": impact_counts,
        "statusLabels": status_order,
        "statusCounts": status_counts,
        "socleLabels": socle_labels,
        "socleCounts": socle_counts,
        "frameworkLabels": framework_labels,
        "frameworkCounts": framework_counts,
        "appStatusLabels": app_status_labels,
        "appStatusCounts": app_status_counts,
    }

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
    gantt_rows.sort(key=lambda r: (not r["isPilot"], r["start"]))

    milestones = db.query(MilestoneModel).order_by(MilestoneModel.milestone_date).all()
    milestones_data = [
        {
            "id": m.id,
            "label": m.label,
            "date": m.milestone_date.isoformat(),
            "project": m.project.name if m.project else None,
        }
        for m in milestones
    ]

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

    recent_audit_log = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(200).all()
    all_users = db.query(UserModel).order_by(UserModel.username).all() if current_role == "admin" else []

    # Indique si Slack est configuré (variable d'environnement)
    slack_configured = bool(os.environ.get("TECHDEBT_SLACK_WEBHOOK_URL", ""))

    return render_template(
        request,
        "index.html",
        {
            "request": request,
            "current_user": current_user,
            "current_role": current_role,
            "role_labels": ROLE_LABELS,
            "all_users": all_users,
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
            "milestones_json": json.dumps(milestones_data, ensure_ascii=False).replace("</", "<\\/"),
            "milestones": milestones,
            "portfolio_rows": portfolio_rows,
            "alerts_overdue": alerts_overdue,
            "alerts_soon": alerts_soon,
            "alerts_stale_pilot": alerts_stale_pilot,
            "soon_days": SOON_DAYS,
            "stale_pilot_days": STALE_PILOT_DAYS,
            "recent_audit_log": recent_audit_log,
            "slack_configured": slack_configured,
        },
    )
