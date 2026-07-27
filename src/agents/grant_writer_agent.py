"""Grant writing assistant using any available LLM with funder-specific templates."""
import os
import re
import json
from src.agents.llm_client import chat, provider_info


FUNDER_TEMPLATES = {
    "NSF": {
        "name": "National Science Foundation (NSF)",
        "country": "USA",
        "sections": ["Project Summary", "Project Description", "Broader Impacts", "Intellectual Merit", "References Cited"],
        "word_limits": {"Project Summary": 250, "Project Description": 15000},
        "tips": ["Emphasize intellectual merit and broader impacts equally", "Use NSF merit review criteria explicitly", "Include convergence research aspects if applicable"],
    },
    "NIH": {
        "name": "National Institutes of Health (NIH)",
        "country": "USA",
        "sections": ["Specific Aims", "Research Strategy (Significance/Innovation/Approach)", "Bibliography", "Human Subjects"],
        "word_limits": {"Specific Aims": 600, "Research Strategy": 12000},
        "tips": ["Lead with strong Specific Aims — reviewers read this first", "Address NIH scoring criteria: Significance, Investigator, Innovation, Approach, Environment", "Include preliminary data whenever possible"],
    },
    "ERC": {
        "name": "European Research Council (ERC)",
        "country": "Europe",
        "sections": ["Extended Synopsis", "Scientific Proposal (State-of-Art/Methodology/Resources)", "CV & Track Record"],
        "word_limits": {"Extended Synopsis": 2000, "Scientific Proposal": 15000},
        "tips": ["Demonstrate 'frontier research' — beyond state of the art", "Show PI's vision and leadership potential", "ERC values high-risk/high-gain proposals"],
    },
    "Wellcome": {
        "name": "Wellcome Trust",
        "country": "UK/Global",
        "sections": ["Plain Language Summary", "Scientific Abstract", "Research Plan", "Team & Resources"],
        "word_limits": {"Plain Language Summary": 300, "Research Plan": 10000},
        "tips": ["Strong emphasis on health impact", "Wellcome values open science and data sharing", "Include patient/public involvement plans"],
    },
    "Gates": {
        "name": "Bill & Melinda Gates Foundation",
        "country": "Global",
        "sections": ["Executive Summary", "Problem Statement", "Proposed Solution", "Implementation Plan", "Evaluation Plan"],
        "word_limits": {"Executive Summary": 500},
        "tips": ["Focus on global health equity and poverty reduction", "Clear theory of change required", "Strong emphasis on measurable outcomes"],
    },
    "DST-SERB": {
        "name": "DST-SERB (India)",
        "country": "India",
        "sections": ["Project Summary", "State of Art", "Objectives", "Methodology", "Work Plan", "Budget Justification"],
        "word_limits": {"Project Summary": 300},
        "tips": ["Link to national priorities in Indian science policy", "Include collaboration with Indian institutions", "SERB values interdisciplinary approaches"],
    },
    "UKRI": {
        "name": "UK Research and Innovation (UKRI)",
        "country": "UK",
        "sections": ["Vision", "Approach", "Applicant & Team", "Resources & Cost", "Ethics & Responsible Innovation"],
        "word_limits": {"Vision": 4000, "Approach": 8000},
        "tips": ["Show clear pathway to impact", "Address responsible innovation framework", "Collaboration with non-academic partners valued"],
    },
}


class GrantWriterAgent:
    def __init__(self):
        info = provider_info()
        if not info["available"]:
            raise RuntimeError(
                "No LLM available for grant writing.\n"
                "Options: ANTHROPIC_API_KEY, GROQ_API_KEY, Ollama (ollama serve), or OPENROUTER_API_KEY"
            )

    def write(self, project_title, description, funder, field, budget="", duration="", team="") -> dict:
        template = FUNDER_TEMPLATES.get(funder, {
            "name": funder, "country": "International",
            "sections": ["Executive Summary", "Background", "Objectives", "Methodology", "Impact", "Budget"],
            "word_limits": {}, "tips": [],
        })

        sections_desc = ", ".join(template["sections"])
        tips = "\n".join(f"- {t}" for t in template.get("tips", []))

        prompt = f"""You are an expert grant writer. Write a compelling grant proposal for:

PROJECT TITLE: {project_title}
FIELD: {field}
FUNDER: {template['name']} ({template['country']})
BUDGET: {budget or 'Not specified'}
DURATION: {duration or 'Not specified'}
TEAM: {team or 'Not specified'}

PROJECT DESCRIPTION:
{description}

FUNDER-SPECIFIC TIPS:
{tips}

Write these sections: {sections_desc}

Be specific, concrete, and avoid vague language. Quantify impact. Show clear innovation.

Return ONLY a JSON object:
{{
  "sections": [
    {{"name": "Project Summary", "content": "Full written content...", "word_count": 245}}
  ],
  "key_innovations": ["Innovation 1", "Innovation 2"],
  "expected_outcomes": ["Outcome 1", "Outcome 2"],
  "budget_notes": "Budget justification guidance",
  "reviewer_tips": ["Tip for strengthening this proposal"]
}}"""

        try:
            raw = chat(prompt, max_tokens=5000).strip()
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                data["funder_info"] = template
                data["project_title"] = project_title
                data["funder"] = funder
                return data
        except Exception as e:
            print(f"Grant writing error: {e}")

        return {"error": "Failed to generate grant proposal", "sections": []}

    @staticmethod
    def get_funders():
        return [
            {"key": k, "name": v["name"], "country": v["country"]}
            for k, v in FUNDER_TEMPLATES.items()
        ]
