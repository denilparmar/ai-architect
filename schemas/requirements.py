"""RequirementSpec: the requirements agent's structured output."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from agent.tools.formula_library import ASSUMPTION_DEFAULTS, FORMULA_LIBRARY

# Allowed values come from formula_library.py so the schema, the calculator
# and the field descriptions can never disagree.
SYSTEM_TYPES = tuple(FORMULA_LIBRARY)
ASSUMPTION_KEYS = tuple(ASSUMPTION_DEFAULTS)

SystemType = Literal[SYSTEM_TYPES]
AssumptionKey = Literal[ASSUMPTION_KEYS]

AWS_REGION_PATTERN = re.compile(r"^[a-z]{2}(-gov)?-[a-z]+-\d+$")


def check_aws_region(region: str) -> str:
    """Return `region` if it looks like an AWS region code, else raise with examples."""
    if not AWS_REGION_PATTERN.match(region):
        raise ValueError(
            f"'{region}' is not an AWS region code. Use codes like ap-south-1, us-east-1 or eu-west-1."
        )
    return region


# A single AWS region code, validated; reused by other schemas (e.g. components.py).
AwsRegion = Annotated[str, AfterValidator(check_aws_region)]

ASSUMPTIONS_DESCRIPTION = (
    "Sizing assumptions relevant to this system type. Use the typical default unless "
    "the user gave a value. Allowed keys and typical defaults: "
    + ", ".join(
        key + "=" + format(value, "g") for key, value in ASSUMPTION_DEFAULTS.items()
    )
)


class ExplicitRequirements(BaseModel):
    """Requirements the user stated directly."""

    model_config = ConfigDict(extra="forbid")

    daily_active_users: int = Field(
        gt=0,
        description="Daily active users exactly as the user stated. Never invent or estimate this value.",
    )
    regions: list[str] = Field(
        default_factory=list,
        description=(
            "AWS region codes where users are. Convert locations the user mentions "
            "(e.g. India → ap-south-1, US East → us-east-1, Europe → eu-west-1). "
            "Empty list if no preference."
        ),
    )
    monthly_budget_usd: float | None = Field(
        default=None,
        gt=0,
        description="Monthly budget ceiling in USD as the user stated it, or null if they chose not to give one.",
    )

    @field_validator("regions")
    @classmethod
    def _check_region_codes(cls, regions: list[str]) -> list[str]:
        for region in regions:
            check_aws_region(region)
        return regions


class RequirementSpec(BaseModel):
    """Structured requirement spec for the system the user wants to design."""

    model_config = ConfigDict(extra="forbid")

    system_type: SystemType = Field(
        description="The category that best matches the user's system."
    )
    explicit_requirements: ExplicitRequirements = Field(
        description="Requirements the user stated directly."
    )
    clarifications: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "The user's answer to each question you asked, keyed by short topic, in their "
            "own words as text (e.g. 'Yes, voice and video'). Always include the budget "
            "answer under 'budget', also when they declined."
        ),
    )
    assumptions: dict[AssumptionKey, Annotated[float, Field(gt=0)]] = Field(
        default_factory=dict,
        description=ASSUMPTIONS_DESCRIPTION,
    )
