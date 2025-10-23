from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import Project

def project_from_path(project_code: str, db: Session = Depends(get_db)) -> Project:
    """
    FastAPI dependency that reads {project_code} from the path, looks up the project in DB, 404s if it doesn’t exist, 
    and injects the Project row into your endpoint so every handler already has the resolved tenant.
    """
    proj = db.query(Project).filter(Project.code == project_code).first()
    if not proj:
        raise HTTPException(404, "project not found")
    return proj
