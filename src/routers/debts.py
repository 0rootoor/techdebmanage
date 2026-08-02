import os
import io
import json
import urllib.request
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import pandas as pd

from database import get_db
from models import TechDebtModel, CommentModel, DebtLinkModel, ProjectModel, log_action
from auth import require_api_auth, require_contributor, require_admin

router = APIRouter(tags=["debts"])

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

@router.post("/api/debts")
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
    user: str = Depends(require_contributor),
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

@router.put("/api/debts/{debt_id}")
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
    user: str = Depends(require_contributor),
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

@router.delete("/api/debts/{debt_id}")
def delete_debt_endpoint(debt_id: int, db: Session = Depends(get_db), user: str = Depends(require_contributor)):
    db_debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    title = db_debt.title
    db.delete(db_debt)
    log_action(db, user, "Dette", title, "Suppression")
    db.commit()
    return {"message": "Dette supprimée"}

@router.patch("/api/debts/{debt_id}/status")
def update_debt_status(debt_id: int, status: str, db: Session = Depends(get_db), user: str = Depends(require_contributor)):
    db_debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    old_status = db_debt.status
    db_debt.status = status
    log_action(db, user, "Dette", db_debt.title, "Changement de statut", f"{old_status} → {status}")
    db.commit()
    return {"message": "Statut mis à jour"}

@router.get("/api/debts/{debt_id}/comments")
def get_comments(debt_id: int, db: Session = Depends(get_db), user: str = Depends(require_api_auth)):
    debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    return [
        {"id": c.id, "username": c.username, "content": c.content, "created_at": c.created_at.strftime("%Y-%m-%d %H:%M")}
        for c in debt.comments
    ]

@router.post("/api/debts/{debt_id}/comments")
def add_comment(debt_id: int, content: str, db: Session = Depends(get_db), user: str = Depends(require_contributor)):
    debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Le commentaire ne peut pas être vide")
    comment = CommentModel(debt_id=debt_id, username=user, content=content.strip())
    db.add(comment)
    log_action(db, user, "Dette", debt.title, "Commentaire", content.strip()[:100])
    db.commit()
    return {"message": "Commentaire ajouté"}

@router.delete("/api/comments/{comment_id}")
def delete_comment(comment_id: int, request: Request, db: Session = Depends(get_db), user: str = Depends(require_contributor)):
    comment = db.query(CommentModel).filter(CommentModel.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Commentaire non trouvé")
    if comment.username != user and request.session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Tu ne peux supprimer que tes propres commentaires")
    db.delete(comment)
    db.commit()
    return {"message": "Commentaire supprimé"}

@router.get("/api/debts/{debt_id}/links")
def get_links(debt_id: int, db: Session = Depends(get_db), user: str = Depends(require_api_auth)):
    debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    return [{"id": l.id, "label": l.label, "url": l.url} for l in debt.links]

@router.post("/api/debts/{debt_id}/links")
def add_link(debt_id: int, label: str, url: str, db: Session = Depends(get_db), user: str = Depends(require_contributor)):
    debt = db.query(TechDebtModel).filter(TechDebtModel.id == debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Dette non trouvée")
    if not label.strip() or not url.strip():
        raise HTTPException(status_code=400, detail="Le libellé et l'URL sont requis")
    if not (url.strip().startswith("http://") or url.strip().startswith("https://")):
        raise HTTPException(status_code=400, detail="L'URL doit commencer par http:// ou https://")
    link = DebtLinkModel(debt_id=debt_id, label=label.strip(), url=url.strip())
    db.add(link)
    log_action(db, user, "Dette", debt.title, "Lien ajouté", label.strip())
    db.commit()
    return {"message": "Lien ajouté"}

@router.delete("/api/links/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db), user: str = Depends(require_contributor)):
    link = db.query(DebtLinkModel).filter(DebtLinkModel.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Lien non trouvé")
    db.delete(link)
    db.commit()
    return {"message": "Lien supprimé"}

@router.get("/api/debts/export")
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

@router.post("/api/alerts/send")
def send_alerts_endpoint(db: Session = Depends(get_db), user: str = Depends(require_contributor)):
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
