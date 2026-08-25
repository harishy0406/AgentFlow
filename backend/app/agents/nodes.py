"""
Agent Nodes — Phase 1 + Phase 3

LangGraph node functions for the six artifact agents. Phase 3 replaces
the hardcoded get_llm() with the Quality-Signal Router, so even the
initial full-pipeline generation picks the best model per artifact type.
"""

from typing import Dict, Any
from langchain_core.prompts import PromptTemplate

from .state import AgentFlowState
from .prompts import (
    BUSINESS_ANALYST_PROMPT,
    SYSTEM_DESIGNER_PROMPT,
    DATABASE_ARCHITECT_PROMPT,
    API_DESIGNER_PROMPT,
    QA_ENGINEER_PROMPT,
    PROJECT_PLANNER_PROMPT,
)
from .provider_registry import PROVIDER_REGISTRY


def _get_llm_for_artifact(artifact_type: str):
    """
    Phase 3: Select the best available model for the given artifact type.
    During initial generation we don't have a DB session in the LangGraph
    state, so we use a simplified version that picks the cheapest available
    model (no historical scores yet on first run).
    """
    candidates = PROVIDER_REGISTRY.models_for(artifact_type)
    if not candidates:
        # Fallback
        return PROVIDER_REGISTRY.get_chat_model("openai", "gpt-4o-mini")

    # On first generation there's no history — pick cheapest available
    cheapest = min(candidates, key=lambda m: m.avg_cost_per_token)
    return PROVIDER_REGISTRY.get_chat_model(cheapest.provider, cheapest.model_name)


def business_analyst_node(state: AgentFlowState) -> AgentFlowState:
    llm = _get_llm_for_artifact("PRD")
    prompt = PromptTemplate.from_template(BUSINESS_ANALYST_PROMPT)
    chain = prompt | llm

    response = chain.invoke({
        "project_brief": state.project_brief,
        "clarifications": state.clarifications or "None provided."
    })
    state.prd = response.content
    return state


def system_designer_node(state: AgentFlowState) -> AgentFlowState:
    llm = _get_llm_for_artifact("SDD")
    prompt = PromptTemplate.from_template(SYSTEM_DESIGNER_PROMPT)
    chain = prompt | llm

    response = chain.invoke({"prd": state.prd})
    state.sdd = response.content
    return state


def database_architect_node(state: AgentFlowState) -> AgentFlowState:
    llm = _get_llm_for_artifact("DB_SCHEMA")
    prompt = PromptTemplate.from_template(DATABASE_ARCHITECT_PROMPT)
    chain = prompt | llm

    response = chain.invoke({"sdd": state.sdd})
    state.db_schema = response.content
    return state


def api_designer_node(state: AgentFlowState) -> AgentFlowState:
    llm = _get_llm_for_artifact("API_SPEC")
    prompt = PromptTemplate.from_template(API_DESIGNER_PROMPT)
    chain = prompt | llm

    response = chain.invoke({
        "sdd": state.sdd,
        "db_schema": state.db_schema,
    })
    state.api_spec = response.content
    return state


def qa_engineer_node(state: AgentFlowState) -> AgentFlowState:
    llm = _get_llm_for_artifact("USER_STORIES")
    prompt = PromptTemplate.from_template(QA_ENGINEER_PROMPT)
    chain = prompt | llm

    response = chain.invoke({
        "prd": state.prd,
        "api_spec": state.api_spec,
    })
    state.user_stories = response.content
    return state


def project_planner_node(state: AgentFlowState) -> AgentFlowState:
    llm = _get_llm_for_artifact("TASKS")
    prompt = PromptTemplate.from_template(PROJECT_PLANNER_PROMPT)
    chain = prompt | llm

    response = chain.invoke({
        "user_stories": state.user_stories,
        "api_spec": state.api_spec,
    })
    state.tasks = response.content
    return state
