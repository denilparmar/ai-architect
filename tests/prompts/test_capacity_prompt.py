import json
import re

from agent.prompts_library import SYSTEM_PROMPTS
from schemas.capacity import SizingTable

PROMPT = SYSTEM_PROMPTS["capacity_calculator_prompt"]


def test_capacity_prompt_example_matches_sizing_table_schema():
    examples = re.findall(
        r"(?:Final output format:|Expected SizingTable output:)\s*"
        r"```json\s*(\{.*?\})\s*```",
        PROMPT,
        re.DOTALL,
    )

    assert len(examples) == 3
    for example in examples:
        result = json.loads(example)
        table = SizingTable.model_validate(result)

        assert table.rows
        assert all(
            set(row) == {"Derived Metric", "Computed From", "Drives"}
            for row in result["rows"]
        )

    assert "Return only a JSON object" in PROMPT
    assert "no Markdown fences or surrounding prose" in PROMPT
    assert '"capacity_table"' not in PROMPT
    assert '"resource_category"' not in PROMPT
