from sqlalchemy import Column, Integer, String, ForeignKey, Date, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import date, datetime
from database import Base

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
    comments = relationship("CommentModel", back_populates="debt", cascade="all, delete-orphan", order_by="CommentModel.created_at")
    links = relationship("DebtLinkModel", back_populates="debt", cascade="all, delete-orphan")

class AuditLogModel(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    username = Column(String)
    entity_type = Column(String)   # "Application" ou "Dette"
    entity_name = Column(String)
    action = Column(String)        # "Création", "Modification", "Suppression", "Changement de statut"
    details = Column(String, nullable=True)

class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String, default="contributeur")  # "admin", "contributeur", "lecture_seule"
    created_at = Column(DateTime, default=datetime.utcnow)

class CommentModel(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    debt_id = Column(Integer, ForeignKey("tech_debts.id"))
    username = Column(String)
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    debt = relationship("TechDebtModel", back_populates="comments")

class DebtLinkModel(Base):
    __tablename__ = "debt_links"
    id = Column(Integer, primary_key=True, index=True)
    debt_id = Column(Integer, ForeignKey("tech_debts.id"))
    label = Column(String)   # ex: "Jira TECH-123", "PR #456"
    url = Column(String)

    debt = relationship("TechDebtModel", back_populates="links")

class MilestoneModel(Base):
    __tablename__ = "milestones"
    id = Column(Integer, primary_key=True, index=True)
    label = Column(String)
    milestone_date = Column(Date)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)  # None = jalon global
    created_by = Column(String, nullable=True)

    project = relationship("ProjectModel")

def log_action(db, username: str, entity_type: str, entity_name: str, action: str, details: str = None):
    """Enregistre une entrée dans l'historique. Ne fait pas de commit : à inclure dans la même transaction que l'action elle-même."""
    entry = AuditLogModel(username=username, entity_type=entity_type, entity_name=entity_name, action=action, details=details)
    db.add(entry)

