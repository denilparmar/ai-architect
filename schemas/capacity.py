"""SizingTable: capacity modeling agent's structured output.

A table of derived metrics (e.g. peak_write_qps). Each row says what the metric is,
what it was computed from, and which downstream components it drives. Rows use the
display names "Derived Metric", "Computed From" and "Drives" as aliases.
"""

from pydantic import BaseModel, ConfigDict, Field


class SizingRow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    derived_metric: str = Field(
        min_length=1,
        alias="Derived Metric",
        description="Name of the derived metric, e.g. 'peak_write_qps'.",
    )
    computed_from: str = Field(
        min_length=1,
        alias="Computed From",
        description="Inputs and formula it was computed from, e.g. 'daily_active_users * messages_per_user_per_day / 86400 * peak_factor'.",
    )
    drives: str = Field(
        min_length=1,
        alias="Drives",
        description="What this metric drives, e.g. 'DynamoDB write capacity, API Gateway throttling'.",
    )


class SizingTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[SizingRow] = Field(min_length=1)
