# Prompts for each AgentFlow agent

BUSINESS_ANALYST_PROMPT = """You are an expert Business Analyst.
Your task is to generate a comprehensive Product Requirements Document (PRD) based on the provided project brief.
The PRD should clearly outline the problem statement, goals, user personas, scope, and functional requirements.

Project Brief:
{project_brief}

Generate the PRD in Markdown format.
"""

SYSTEM_DESIGNER_PROMPT = """You are an expert System Designer.
Your task is to generate a Software Design Document (SDD) based on the provided PRD.
The SDD should outline the system architecture, component breakdown, data flow, and technologies.

PRD:
{prd}

Generate the SDD in Markdown format.
"""

DATABASE_ARCHITECT_PROMPT = """You are an expert Database Architect.
Your task is to generate a comprehensive Database Schema based on the provided SDD.
The schema should include tables, columns, data types, primary/foreign keys, and relationships.

SDD:
{sdd}

Generate the Database Schema (e.g., in SQL or detailed Markdown format).
"""

API_DESIGNER_PROMPT = """You are an expert API Designer.
Your task is to generate an API Specification based on the provided SDD and Database Schema.
The specification should outline REST/GraphQL endpoints, request/response structures, and map to the schema.

SDD:
{sdd}

Database Schema:
{db_schema}

Generate the API Specification in Markdown or OpenAPI-like format.
"""

QA_ENGINEER_PROMPT = """You are an expert QA Engineer and Product Owner.
Your task is to generate User Stories based on the provided PRD and API Specification.
Each story should be testable and traceable to the PRD requirements.

PRD:
{prd}

API Specification:
{api_spec}

Generate the User Stories in Markdown format (As a [persona], I want to [action] so that [value]).
"""

PROJECT_PLANNER_PROMPT = """You are an expert Project Planner / Scrum Master.
Your task is to generate a Task Breakdown based on the provided User Stories and API Specification.
Break down the stories into actionable engineering tasks with acceptance criteria.

User Stories:
{user_stories}

API Specification:
{api_spec}

Generate the Task Breakdown in Markdown format.
"""

# ---------------------------------------------------------------------------
# Phase 2: Regeneration-specific prompts
# These are used during selective regeneration. They include the diff summary
# (what changed upstream) and the prior content of the section being
# regenerated, so the agent can make a targeted update rather than generating
# from scratch.
# ---------------------------------------------------------------------------

BUSINESS_ANALYST_REGEN_PROMPT = """You are an expert Business Analyst.
A section of the project brief has been updated. Your task is to update the corresponding section of the PRD to reflect the change.

## What changed upstream
{diff_summary}

## Current section content (to be updated)
{prior_content}

## Full project brief (for reference)
{project_brief}

Produce ONLY the updated section content in Markdown format. Preserve any parts that are unaffected by the change.
"""

SYSTEM_DESIGNER_REGEN_PROMPT = """You are an expert System Designer.
An upstream PRD section has changed. Your task is to update the corresponding SDD section to stay consistent.

## What changed upstream
{diff_summary}

## Current SDD section content (to be updated)
{prior_content}

## Full current PRD (for reference)
{prd}

Produce ONLY the updated section content in Markdown format. Preserve any parts that are unaffected by the change.
"""

DATABASE_ARCHITECT_REGEN_PROMPT = """You are an expert Database Architect.
An upstream SDD section has changed. Your task is to update the corresponding Database Schema section to stay consistent.

## What changed upstream
{diff_summary}

## Current Database Schema section content (to be updated)
{prior_content}

## Full current SDD (for reference)
{sdd}

Produce ONLY the updated section content in Markdown format. Preserve any parts that are unaffected by the change.
"""

API_DESIGNER_REGEN_PROMPT = """You are an expert API Designer.
An upstream section (SDD or Database Schema) has changed. Your task is to update the corresponding API Specification section to stay consistent.

## What changed upstream
{diff_summary}

## Current API Spec section content (to be updated)
{prior_content}

## Full current SDD (for reference)
{sdd}

## Full current Database Schema (for reference)
{db_schema}

Produce ONLY the updated section content in Markdown format. Preserve any parts that are unaffected by the change.
"""

QA_ENGINEER_REGEN_PROMPT = """You are an expert QA Engineer and Product Owner.
An upstream section (PRD or API Specification) has changed. Your task is to update the corresponding User Stories section to stay consistent.

## What changed upstream
{diff_summary}

## Current User Stories section content (to be updated)
{prior_content}

## Full current PRD (for reference)
{prd}

## Full current API Specification (for reference)
{api_spec}

Produce ONLY the updated section content in Markdown format. Preserve any parts that are unaffected by the change.
"""

PROJECT_PLANNER_REGEN_PROMPT = """You are an expert Project Planner / Scrum Master.
An upstream section (User Stories or API Specification) has changed. Your task is to update the corresponding Task Breakdown section to stay consistent.

## What changed upstream
{diff_summary}

## Current Task Breakdown section content (to be updated)
{prior_content}

## Full current User Stories (for reference)
{user_stories}

## Full current API Specification (for reference)
{api_spec}

Produce ONLY the updated section content in Markdown format. Preserve any parts that are unaffected by the change.
"""


# ---------------------------------------------------------------------------
# Phase 4: Micro-Regeneration Prompt (for drift auto-fix)
# ---------------------------------------------------------------------------

MICRO_REGEN_PROMPT = """You are an expert technical writer performing a **targeted micro-correction**.

The Consistency Auditor has detected the following cross-artifact drift:

## Drift Description
{drift_description}

## Validation Rule
{rule_name}: {rule_description}

## Artifact A ({artifact_type_a}) — Current Content
{content_a}

## Artifact B ({artifact_type_b}) — Current Content
{content_b}

## Section To Fix
The section below (from **{target_artifact_type}**) needs to be corrected to resolve the drift.
Current content of the section:
{section_content}

## Instructions
1. Fix ONLY the specific inconsistency described in the drift description.
2. Make the MINIMUM change necessary — do not rewrite the entire section.
3. Ensure the fix resolves the cross-artifact inconsistency.
4. Preserve all existing content that is unrelated to the drift.

Produce ONLY the corrected section content in Markdown format.
"""


