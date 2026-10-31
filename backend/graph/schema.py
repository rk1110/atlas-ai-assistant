"""What the knowledge graph may contain. A fixed vocabulary keeps the graph consistent:
without one, a model invents "MANAGES", "IS_HEAD_OF" and "LEADS" for the same thing, and
the graph can't be queried reliably. These types are also safe to put in Cypher queries,
because nothing outside this list is ever accepted.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

EntityType = Literal["Person", "Team", "Policy", "System", "Channel", "Office", "Company"]

RelationType = Literal[
    "LEADS",  # Person -> Team
    "REPORTS_TO",  # Person -> Person
    "MEMBER_OF",  # Person -> Team
    "PART_OF",  # Team -> Team / Company, Office -> Company
    "OWNS",  # Team -> Policy / System / document
    "APPROVES",  # Person / Team -> Policy (an approval step it describes)
    "HANDLES",  # Team -> Channel / System (where a team takes requests)
    "CONTACT_FOR",  # Person / Team / Channel -> Policy (who to ask about it)
    "USES",  # Policy -> System (e.g. Expense Policy uses the expense tool)
    "REFERENCES",  # Policy -> Policy
    "LOCATED_IN",  # Person / Team -> Office
]

# How a relation reads in a sentence: "Elena Petrova leads Finance Team".
VERBS: dict[str, str] = {
    "LEADS": "leads",
    "REPORTS_TO": "reports to",
    "MEMBER_OF": "is a member of",
    "PART_OF": "is part of",
    "OWNS": "owns",
    "APPROVES": "approves requests under",
    "HANDLES": "handles requests via",
    "CONTACT_FOR": "is the contact for",
    "USES": "uses",
    "REFERENCES": "refers to",
    "LOCATED_IN": "is located in",
}


def entity_key(name: str) -> str:
    """Entity resolution, the simple version: one node per case/space-normalised name, so
    "Finance team" in one document and "Finance Team" in another become the same node."""
    return " ".join(name.lower().split())


class Entity(BaseModel):
    name: str = Field(
        description="Canonical full name, e.g. 'Elena Petrova', 'Finance Team', 'Expense Policy'."
    )
    type: EntityType
    description: str = Field(
        default="", description="A few words, e.g. 'Finance Manager' or 'Slack channel'."
    )

    @field_validator("name")
    @classmethod
    def strip(cls, value: str) -> str:
        return " ".join(value.split())


class Relation(BaseModel):
    source: str = Field(description="Name of the entity the relation starts from.")
    type: RelationType
    target: str = Field(description="Name of the entity the relation points to.")
    evidence: str = Field(description="The sentence from the document that states it.")


class Extraction(BaseModel):
    """What one document contributes to the graph. Entities first: the model then writes
    relations between names it has already listed (field order steers generation)."""

    entities: list[Entity]
    relations: list[Relation]
