from typing import Dict, Any
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from .state import AgentFlowState
from .prompts import (
    BUSINESS_ANALYST_PROMPT,
    SYSTEM_DESIGNER_PROMPT,
    DATABASE_ARCHITECT_PROMPT,
    API_DESIGNER_PROMPT,
    QA_ENGINEER_PROMPT,
    PROJECT_PLANNER_PROMPT
)

# In Phase 1, we use a single model abstraction. 
# We'll default to OpenAI (e.g. gpt-4o-mini) assuming the user sets OPENAI_API_KEY.
# The routing logic (Phase 3) will later expand this to be dynamic based on the state.

def get_llm():
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)

def business_analyst_node(state: AgentFlowState) -> AgentFlowState:
    llm = get_llm()
    prompt = PromptTemplate.from_template(BUSINESS_ANALYST_PROMPT)
    chain = prompt | llm
    
    response = chain.invoke({"project_brief": state.project_brief})
    state.prd = response.content
    return state

def system_designer_node(state: AgentFlowState) -> AgentFlowState:
    llm = get_llm()
    prompt = PromptTemplate.from_template(SYSTEM_DESIGNER_PROMPT)
    chain = prompt | llm
    
    response = chain.invoke({"prd": state.prd})
    state.sdd = response.content
    return state

def database_architect_node(state: AgentFlowState) -> AgentFlowState:
    llm = get_llm()
    prompt = PromptTemplate.from_template(DATABASE_ARCHITECT_PROMPT)
    chain = prompt | llm
    
    response = chain.invoke({"sdd": state.sdd})
    state.db_schema = response.content
    return state

def api_designer_node(state: AgentFlowState) -> AgentFlowState:
    llm = get_llm()
    prompt = PromptTemplate.from_template(API_DESIGNER_PROMPT)
    chain = prompt | llm
    
    response = chain.invoke({
        "sdd": state.sdd, 
        "db_schema": state.db_schema
    })
    state.api_spec = response.content
    return state

def qa_engineer_node(state: AgentFlowState) -> AgentFlowState:
    llm = get_llm()
    prompt = PromptTemplate.from_template(QA_ENGINEER_PROMPT)
    chain = prompt | llm
    
    response = chain.invoke({
        "prd": state.prd, 
        "api_spec": state.api_spec
    })
    state.user_stories = response.content
    return state

def project_planner_node(state: AgentFlowState) -> AgentFlowState:
    llm = get_llm()
    prompt = PromptTemplate.from_template(PROJECT_PLANNER_PROMPT)
    chain = prompt | llm
    
    response = chain.invoke({
        "user_stories": state.user_stories, 
        "api_spec": state.api_spec
    })
    state.tasks = response.content
    return state
