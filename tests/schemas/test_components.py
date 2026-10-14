import copy
import json
from typing import get_args

import pytest
from pydantic import ValidationError

from schemas import (
    AWS_SERVICES,
    AwsComponent,
    AwsDesign,
    ComponentChoices,
    RequirementSpec,
    unknown_references,
)
from schemas.components import AWS_COMPONENT_MODELS

# The spec the WhatsApp design below was made from; its references must all resolve.
SPEC = RequirementSpec.model_validate(
    {
        "system_type": "messaging / chat apps",
        "explicit_requirements": {
            "daily_active_users": 1_000_000,
            "regions": ["ap-south-1", "us-east-1"],
        },
        "clarifications": {"voice_video": "Yes, voice and video", "budget": "Declined"},
        "assumptions": {"messages_per_user_per_day": 40},
    }
)


def region_components(region):
    return [
        {
            "id": f"app-{region}",
            "service": "ec2",
            "region": region,
            "instance_type": "m7i.large",
            "count": 6,
            "rationale": "Stateless chat servers sized for peak message fan-out in this region.",
            "based_on": [
                "requirement:daily_active_users",
                "assumption:messages_per_user_per_day",
                "sizing:peak_write_qps",
            ],
        },
        {
            "id": f"db-{region}",
            "service": "rds",
            "region": region,
            "engine": "postgres",
            "instance_type": "db.r7g.large",
            "multi_az": True,
            "rationale": "Multi-AZ Postgres keeps account and contact data available through an AZ failure.",
            "based_on": ["requirement:regions", "kb:rds-multi-az"],
        },
        {
            "id": f"cache-{region}",
            "service": "elasticache",
            "region": region,
            "engine": "valkey",
            "instance_type": "cache.r7g.large",
            "count": 2,
            "rationale": "Valkey holds presence and session state that is read on every message.",
            "based_on": ["assumption:messages_per_user_per_day"],
        },
        {
            "id": f"media-{region}",
            "service": "s3",
            "region": region,
            "rationale": "S3 Standard stores voice notes and media shared in chats.",
            "based_on": ["clarification:voice_video"],
        },
        {
            "id": f"egress-{region}",
            "service": "data_transfer",
            "region": region,
            "direction": "internet",
            "rationale": "Media and message delivery to users leaves AWS to the internet.",
            "based_on": ["requirement:daily_active_users", "clarification:voice_video"],
        },
    ]


WHATSAPP = {
    "components": region_components("ap-south-1") + region_components("us-east-1")
}

# One minimal valid component per service: only the fields that have no default.
MINIMAL = {
    "ec2": {"instance_type": "m7i.large"},
    "ebs": {},
    "nat_gateway": {},
    "fargate": {"vcpu": 1, "memory_gb": 2},
    "eks": {},
    "lambda": {"memory_mb": 512},
    "api_gateway": {"api_type": "http"},
    "load_balancer": {"lb_type": "application"},
    "cloudfront": {"edge_geography": "india"},
    "rds": {"engine": "postgres", "instance_type": "db.r7g.large"},
    "dynamodb": {},
    "elasticache": {"engine": "valkey", "instance_type": "cache.r7g.large"},
    "s3": {},
    "sqs": {},
    "sns": {},
    "cloudwatch": {},
    "data_transfer": {"direction": "internet"},
}

# One Literal field per service that has any, with a value outside its allowed set.
WRONG_LITERAL = {
    "ec2": ("operating_system", "macos"),
    "ebs": ("volume_type", "io1"),
    "fargate": ("cpu_architecture", "arm"),
    "lambda": ("architecture", "aarch64"),
    "api_gateway": ("api_type", "websocket"),
    "load_balancer": ("lb_type", "gateway"),
    "cloudfront": ("edge_geography", "ap-south-1"),
    "rds": ("engine", "oracle"),
    "dynamodb": ("capacity_mode", "serverless"),
    "elasticache": ("engine", "postgres"),
    "s3": ("storage_class", "glacier"),
    "sqs": ("queue_type", "priority"),
    "data_transfer": ("direction", "outbound"),
}

# Usage quantities belong to sizing, not to this contract.
USAGE_FIELDS = (
    "storage_gb",
    "monthly_gb",
    "gb_per_month",
    "hours_per_month",
    "requests_per_month",
    "usage",
)


def one(service, **changes):
    component = {
        "id": f"{service}-1",
        "service": service,
        "region": "ap-south-1",
        "rationale": "Chosen to meet the stated daily active users.",
        "based_on": ["requirement:daily_active_users"],
    }
    component.update(MINIMAL[service])
    component.update(changes)
    return {"components": [component]}


def parse_one(service, **changes):
    return ComponentChoices.model_validate(one(service, **changes)).components[0]


def error_text(data):
    with pytest.raises(ValidationError) as exc:
        ComponentChoices.model_validate(data)
    return str(exc.value)


def test_component_choices_is_the_aws_envelope():
    assert ComponentChoices is AwsDesign


def test_valid_whatsapp_choices_parse():
    choices = ComponentChoices.model_validate(WHATSAPP)
    assert len(choices.components) == 10
    assert {c.region for c in choices.components} == {"ap-south-1", "us-east-1"}


def test_every_service_has_a_minimal_example_and_a_model():
    assert set(MINIMAL) == set(AWS_SERVICES)
    assert len(AWS_SERVICES) == 17
    union_members = get_args(get_args(AwsComponent)[0])
    assert set(union_members) == set(AWS_COMPONENT_MODELS)


@pytest.mark.parametrize("service", AWS_SERVICES)
def test_minimal_component_per_service_parses_to_its_model(service):
    component = parse_one(service)
    model = AWS_COMPONENT_MODELS[AWS_SERVICES.index(service)]
    assert type(component) is model
    assert component.service == service


def test_defaults():
    ec2 = parse_one("ec2")
    assert (ec2.count, ec2.operating_system) == (1, "linux")
    rds = parse_one("rds")
    assert (rds.multi_az, rds.storage_type, rds.count) == (False, "gp3", 1)
    assert parse_one("dynamodb").capacity_mode == "on_demand"
    assert parse_one("sqs").queue_type == "standard"
    assert parse_one("fargate").cpu_architecture == "x86_64"


@pytest.mark.parametrize("service", list(WRONG_LITERAL))
def test_wrong_literal_value_rejected(service):
    field, value = WRONG_LITERAL[service]
    text = error_text(one(service, **{field: value}))
    assert f"components.0.{service}.{field}" in text


def test_engine_of_the_other_service_lists_valid_engines():
    text = error_text(one("rds", engine="redis"))
    assert "'postgres', 'mysql' or 'mariadb'" in text


@pytest.mark.parametrize("service", AWS_SERVICES)
@pytest.mark.parametrize("field", ["storage_gb", "hours_per_month"])
def test_extra_field_rejected(service, field):
    text = error_text(one(service, **{field: 100}))
    assert "Extra inputs are not permitted" in text


@pytest.mark.parametrize(
    ("service", "field"),
    [(s, f) for s, fields in MINIMAL.items() for f in fields],
)
def test_missing_required_field_rejected(service, field):
    data = one(service)
    del data["components"][0][field]
    assert "Field required" in error_text(data)


@pytest.mark.parametrize("service", AWS_SERVICES)
def test_explicit_nulls_tolerated(service):
    # None on a field the model may have (to_region) and on fields it lacks.
    component = parse_one(service, to_region=None, storage_gb=None, citation=None)
    assert component.service == service


def test_explicit_null_on_required_field_is_still_missing():
    assert "Field required" in error_text(one("rds", engine=None))


def test_old_citation_field_rejected():
    text = error_text(one("s3", citation="https://docs.aws.amazon.com/s3/"))
    assert "Extra inputs are not permitted" in text


# --- provenance: rationale + based_on (enforced by the base class for every service)


@pytest.mark.parametrize("service", AWS_SERVICES)
@pytest.mark.parametrize("field", ["id", "region", "rationale", "based_on"])
def test_common_field_required_for_every_service(service, field):
    data = one(service)
    del data["components"][0][field]
    assert "Field required" in error_text(data)


@pytest.mark.parametrize("rationale", ["", "Because.", "x" * 19])
def test_short_rationale_rejected(rationale):
    text = error_text(one("ec2", rationale=rationale))
    assert "at least 20 characters" in text


def test_null_rationale_is_missing():
    assert "Field required" in error_text(one("ec2", rationale=None))


def test_empty_based_on_rejected():
    assert "at least 1 item" in error_text(one("ec2", based_on=[]))


@pytest.mark.parametrize(
    "reference",
    [
        "doc:rds-multi-az",  # unknown prefix
        "requirement",  # no key
        "requirement:",  # empty key
        "clarification:Voice Video",  # uppercase and space
        "https://docs.aws.amazon.com/rds/",  # a URL is not a reference
        " sizing:peak_write_qps",  # leading space
    ],
)
def test_bad_reference_rejected(reference):
    text = error_text(
        one("ec2", based_on=["requirement:daily_active_users", reference])
    )
    assert "based_on.1" in text
    assert "should match pattern" in text


@pytest.mark.parametrize(
    "reference",
    [
        "requirement:daily_active_users",
        "clarification:voice_video",
        "assumption:messages_per_user_per_day",
        "sizing:peak_write_qps",
        "kb:rds-multi-az",
    ],
)
def test_each_reference_prefix_accepted(reference):
    assert parse_one("ec2", based_on=[reference]).based_on == [reference]


def test_unknown_references_passes_valid_design():
    assert unknown_references(ComponentChoices.model_validate(WHATSAPP), SPEC) == []


def test_unknown_references_finds_missing_clarification_key():
    data = copy.deepcopy(WHATSAPP)
    data["components"][3]["based_on"] = ["clarification:media_retention"]
    design = ComponentChoices.model_validate(data)
    assert unknown_references(design, SPEC) == [
        "media-ap-south-1: clarification:media_retention"
    ]


def test_unknown_references_checks_requirements_and_assumptions():
    design = ComponentChoices.model_validate(
        one(
            "ec2",
            based_on=[
                "requirement:monthly_budget_usd",  # a real field, but null in SPEC
                "requirement:peak_users",  # not a field
                "assumption:avg_followers",  # allowed key, not in SPEC.assumptions
                "assumption:messages_per_user_per_day",  # present
            ],
        )
    )
    assert unknown_references(design, SPEC) == [
        "ec2-1: requirement:monthly_budget_usd",
        "ec2-1: requirement:peak_users",
        "ec2-1: assumption:avg_followers",
    ]


def test_unknown_references_does_not_report_sizing_or_kb():
    design = ComponentChoices.model_validate(
        one("ec2", based_on=["sizing:made_up_metric", "kb:made-up-doc"])
    )
    assert unknown_references(design, SPEC) == []


def test_provider_defaults_to_aws():
    choices = ComponentChoices.model_validate(one("s3"))
    assert choices.provider == "aws"
    assert choices.model_dump()["provider"] == "aws"


def test_other_provider_rejected():
    data = one("s3")
    data["provider"] = "azure"
    error_text(data)


def test_unknown_service_rejected_with_allowed_tags():
    data = one("s3")
    data["components"][0]["service"] = "redshift"
    text = error_text(data)
    assert "does not match any of the expected tags" in text
    assert "'data_transfer'" in text


def test_bad_region_rejected_with_examples():
    assert "ap-south-1" in error_text(one("ec2", region="Mumbai"))


@pytest.mark.parametrize("service", ["ec2", "ebs", "fargate", "rds", "elasticache"])
def test_zero_count_rejected(service):
    error_text(one(service, count=0))


@pytest.mark.parametrize(
    ("field", "value"),
    [("vcpu", 0.1), ("vcpu", 32), ("memory_gb", 0), ("memory_gb", 200)],
)
def test_fargate_task_size_out_of_range_rejected(field, value):
    error_text(one("fargate", **{field: value}))


def test_fargate_windows_on_arm_rejected():
    text = error_text(
        one("fargate", operating_system="windows", cpu_architecture="arm64")
    )
    assert "windows tasks run on x86_64 only" in text


@pytest.mark.parametrize("memory_mb", [64, 20000])
def test_lambda_memory_out_of_range_rejected(memory_mb):
    error_text(one("lambda", memory_mb=memory_mb))


def test_data_transfer_inter_region_requires_to_region():
    text = error_text(one("data_transfer", direction="inter_region"))
    assert "inter_region data transfer requires to_region" in text


def test_data_transfer_inter_region_with_to_region_parses():
    component = parse_one(
        "data_transfer", direction="inter_region", to_region="us-east-1"
    )
    assert component.to_region == "us-east-1"


def test_data_transfer_to_same_region_rejected():
    text = error_text(
        one("data_transfer", direction="inter_region", to_region="ap-south-1")
    )
    assert "to_region must differ from region" in text


@pytest.mark.parametrize("direction", ["internet", "cross_az"])
def test_data_transfer_to_region_only_for_inter_region(direction):
    text = error_text(one("data_transfer", direction=direction, to_region="us-east-1"))
    assert "only used when direction is inter_region" in text


def test_bad_to_region_rejected():
    error_text(one("data_transfer", direction="inter_region", to_region="Virginia"))


def test_extra_top_level_key_rejected():
    data = copy.deepcopy(WHATSAPP)
    data["total_cost"] = 100
    error_text(data)


def test_duplicate_ids_rejected_and_named():
    data = copy.deepcopy(WHATSAPP)
    data["components"][1]["id"] = data["components"][0]["id"]
    assert "duplicate component ids: app-ap-south-1" in error_text(data)


def test_empty_component_list_rejected():
    error_text({"components": []})


def test_json_round_trip():
    choices = ComponentChoices.model_validate(WHATSAPP)
    again = ComponentChoices.model_validate(choices.model_dump(mode="json"))
    assert again == choices


def test_json_schema_is_a_discriminated_union_of_every_service():
    schema = ComponentChoices.model_json_schema()
    items = schema["properties"]["components"]["items"]
    assert set(items["discriminator"]["mapping"]) == set(AWS_SERVICES)
    assert len(items["oneOf"]) == 17


def test_json_schema_has_no_usage_fields():
    text = json.dumps(ComponentChoices.model_json_schema())
    for field in USAGE_FIELDS:
        assert f'"{field}"' not in text
