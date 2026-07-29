from langgraph.graph import StateGraph, END
from .state import AgentFlowState
from .nodes import (
    business_analyst_node,
    system_designer_node,
    database_architect_node,
    api_designer_node,
    qa_engineer_node,
    project_planner_node
)

def build_graph() -> StateGraph:
    workflow = StateGraph(AgentFlowState)

    # Add all nodes
    workflow.add_node("business_analyst", business_analyst_node)
    workflow.add_node("system_designer", system_designer_node)
    workflow.add_node("database_architect", database_architect_node)
    workflow.add_node("api_designer", api_designer_node)
    workflow.add_node("qa_engineer", qa_engineer_node)
    workflow.add_node("project_planner", project_planner_node)

    # Define edges (Sequential pipeline for Phase 1)
    workflow.set_entry_point("business_analyst")
    
    workflow.add_edge("business_analyst", "system_designer")
    
    # SDD leads to both Database Schema and API Spec (partially)
    # But API Spec needs Database Schema. So sequentially:
    # PRD -> SDD -> Database Schema -> API Spec -> User Stories -> Tasks
    
    workflow.add_edge("system_designer", "database_architect")
    workflow.add_edge("database_architect", "api_designer")
    workflow.add_edge("api_designer", "qa_engineer")
    workflow.add_edge("qa_engineer", "project_planner")
    
    workflow.add_edge("project_planner", END)
    
    return workflow.compile()
