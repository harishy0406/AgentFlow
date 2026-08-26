from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class AgentFlowState(BaseModel):
    project_id: str
    project_name: str
    project_brief: str
    clarifications: Optional[str] = None
    
    # Artifacts stored as strings or dicts depending on complexity
    prd: Optional[str] = None
    sdd: Optional[str] = None
    db_schema: Optional[str] = None
    api_spec: Optional[str] = None
    user_stories: Optional[str] = None
    tasks: Optional[str] = None
    code_generation: Optional[str] = None
    
    # Track the current active model provider (simplified for Phase 1)
    current_model: str = "openai"

