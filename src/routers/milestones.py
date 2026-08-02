from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import MilestoneModel, log_action
from auth import require_contributor

router = APIRouter(tags=["milestones"])

@router.post("/api/milestones")
def create_milestone(
    label: str,
    milestone_date: str,
    project_id: int = None,
    db: Session = Depends(get_db),
    user: str = Depends(require_contributor),
):
    if not label.strip():
        raise HTTPException(status_code=400, detail="Le libellé du jalon est requis")
    try:
        m_date = datetime.strptime(milestone_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Date invalide")
    milestone = MilestoneModel(label=label.strip(), milestone_date=m_date, project_id=project_id, created_by=user)
    db.add(milestone)
    log_action(db, user, "Jalon", label.strip(), "Création", m_date.isoformat())
    db.commit()
    return {"message": "Jalon ajouté"}

@router.delete("/api/milestones/{milestone_id}")
def delete_milestone(milestone_id: int, db: Session = Depends(get_db), user: str = Depends(require_contributor)):
    milestone = db.query(MilestoneModel).filter(MilestoneModel.id == milestone_id).first()
    if not milestone:
        raise HTTPException(status_code=404, detail="Jalon non trouvé")
    label = milestone.label
    db.delete(milestone)
    log_action(db, user, "Jalon", label, "Suppression")
    db.commit()
    return {"message": "Jalon supprimé"}
