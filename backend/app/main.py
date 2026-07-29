from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from . import models, schemas
from .database import engine, get_db

# Create database tables (in a real app, use alembic)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AgentFlow API")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "AgentFlow API is running"}

@app.post("/projects/", response_model=schemas.Project)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    db_project = models.Project(name=project.name, brief=project.brief)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    
    # In a full implementation, we would trigger the initial LangGraph generation here
    
    return db_project

@app.get("/projects/{project_id}", response_model=schemas.Project)
def read_project(project_id: UUID, db: Session = Depends(get_db)):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return db_project
