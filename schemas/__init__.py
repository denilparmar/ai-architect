"""Structured output schemas for every agent, one module per agent output.

Rule: this package holds data shapes only. It must not import agents, db_store,
memory or llm code, so tools, tests and scripts can import it safely. Its only
allowed project import is agent/tools/formula_library.py (a plain-dict module).

Modules:
    requirements.py  RequirementSpec      (requirements agent)
    components.py    ComponentChoices     (component selection agent → cost estimation;
                                           AwsDesign, a per-service union on `service`)
    capacity.py      SizingTable          (capacity modeling agent)
Planned:
    cost.py           CostBreakdown        (cost estimation agent)
    topology.py      TopologyGraph        (architecture composer agent)
    findings.py      Findings             (design critic agent)
"""

from schemas.capacity import SizingRow, SizingTable
from schemas.components import (
    AWS_SERVICES,
    AwsComponent,
    AwsDesign,
    ComponentChoices,
    unknown_references,
)
from schemas.requirements import (
    ASSUMPTION_KEYS,
    SYSTEM_TYPES,
    AssumptionKey,
    AwsRegion,
    ExplicitRequirements,
    RequirementSpec,
    SystemType,
)

__all__ = [
    "ASSUMPTION_KEYS",
    "AWS_SERVICES",
    "SYSTEM_TYPES",
    "AssumptionKey",
    "AwsComponent",
    "AwsDesign",
    "AwsRegion",
    "ComponentChoices",
    "ExplicitRequirements",
    "RequirementSpec",
    "SizingRow",
    "SizingTable",
    "SystemType",
    "unknown_references",
]
