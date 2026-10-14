"""ComponentChoices: component selection's structured output, consumed by cost estimation.

The contract holds SELECTION fields only: what to buy (service, engine, instance type,
architecture, ...), never how much is used. Every field here is filled by the
component-selection LLM; usage numbers (hours, GB, requests) come from capacity/sizing
in code, so the LLM is never asked to guess them.

Each AWS service is its own model, tagged by `service`, with exactly the fields that
select its Price List SKU (see docs/research/aws-pricing/report.md). An unknown field
is rejected; an explicit null is dropped, so it behaves like an omitted field.

Provenance: every component carries a `rationale` and `based_on` references
(requirement:, clarification:, assumption:, sizing:, kb:), so each choice can be backed
up when the user questions it. unknown_references() checks the first three against the
RequirementSpec the design was made from.

Provider envelope: ComponentChoices is AwsDesign today. A second cloud is added later
without touching the AWS models, by writing a sibling envelope and switching the alias
to a union discriminated on `provider`:

    class AzureDesign(BaseModel):
        provider: Literal["azure"] = "azure"
        components: list[AzureComponent] = Field(min_length=1)

    ComponentChoices = Annotated[
        AwsDesign | AzureDesign, Field(discriminator="provider")
    ]

Once that union exists, `provider` must be present in the input (a discriminator is
read from the data, not from the default).
"""

from collections import Counter
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.requirements import AwsRegion, RequirementSpec

OperatingSystem = Literal["linux", "windows"]
CpuArchitecture = Literal["x86_64", "arm64"]


REFERENCE_PREFIXES = ("requirement", "clarification", "assumption", "sizing", "kb")
REFERENCE_PATTERN = r"^(requirement|clarification|assumption|sizing|kb):[a-z0-9_\-]+$"

Reference = Annotated[str, Field(pattern=REFERENCE_PATTERN)]


class _AwsComponent(BaseModel):
    """Fields shared by every AWS component.

    Every service model inherits from this class, and this is the one place the common
    mandatory fields are enforced: id, region, rationale and based_on are required for
    every service, so a component can always be traced back to why it was chosen.
    Service models add only their own selection fields.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        description="Stable, unique key for this component (e.g. 'db-primary-ap-south-1'); cost line items refer to it.",
    )
    region: AwsRegion = Field(
        description="AWS region code this component runs in, e.g. ap-south-1."
    )
    rationale: str = Field(
        min_length=20,
        description="Why this component and these selection values, in 1-2 sentences.",
    )
    based_on: list[Reference] = Field(
        min_length=1,
        description=(
            "References this choice rests on, as prefix:key. Prefixes: "
            "requirement:<field of explicit_requirements> (e.g. requirement:daily_active_users), "
            "clarification:<clarifications key> (e.g. clarification:voice_video), "
            "assumption:<assumptions key> (e.g. assumption:messages_per_user_per_day), "
            "sizing:<sizing metric> (e.g. sizing:peak_write_qps), "
            "kb:<knowledge-base document id> (e.g. kb:rds-multi-az). "
            "Lowercase letters, digits, _ and - only."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        # LLMs often send every field they have seen, as null; treat that as omitted.
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class Ec2(_AwsComponent):
    """Amazon EC2 instances (shared tenancy, no pre-installed software)."""

    service: Literal["ec2"]
    instance_type: str = Field(
        min_length=1, description="EC2 instance type, e.g. m7i.large."
    )
    operating_system: OperatingSystem = "linux"
    count: int = Field(default=1, ge=1, description="Number of identical instances.")


class Ebs(_AwsComponent):
    """Amazon EBS volumes."""

    service: Literal["ebs"]
    volume_type: Literal["gp3", "gp2", "io2", "st1", "sc1"] = "gp3"
    count: int = Field(default=1, ge=1, description="Number of identical volumes.")


class NatGateway(_AwsComponent):
    """NAT gateways."""

    service: Literal["nat_gateway"]
    count: int = Field(default=1, ge=1, description="Number of NAT gateways.")


class Fargate(_AwsComponent):
    """ECS/EKS tasks on AWS Fargate; vcpu and memory_gb are the task size."""

    service: Literal["fargate"]
    cpu_architecture: CpuArchitecture = "x86_64"
    operating_system: OperatingSystem = "linux"
    vcpu: float = Field(ge=0.25, le=16, description="vCPUs per task, 0.25 to 16.")
    memory_gb: float = Field(
        ge=0.5, le=120, description="Memory per task in GB, 0.5 to 120."
    )
    count: int = Field(default=1, ge=1, description="Number of running tasks.")

    @model_validator(mode="after")
    def _windows_is_x86(self) -> "Fargate":
        if self.operating_system == "windows" and self.cpu_architecture != "x86_64":
            raise ValueError("Fargate windows tasks run on x86_64 only")
        return self


class Eks(_AwsComponent):
    """Amazon EKS control planes (worker capacity is a separate ec2 or fargate component)."""

    service: Literal["eks"]
    count: int = Field(default=1, ge=1, description="Number of EKS clusters.")


class Lambda(_AwsComponent):
    """AWS Lambda function(s) with one memory setting."""

    service: Literal["lambda"]
    architecture: CpuArchitecture = "x86_64"
    memory_mb: int = Field(
        ge=128, le=10240, description="Memory per function in MB, 128 to 10240."
    )


class ApiGateway(_AwsComponent):
    """Amazon API Gateway API."""

    service: Literal["api_gateway"]
    api_type: Literal["http", "rest"]


class LoadBalancer(_AwsComponent):
    """Elastic Load Balancing load balancers."""

    service: Literal["load_balancer"]
    lb_type: Literal["application", "network"]
    count: int = Field(default=1, ge=1, description="Number of load balancers.")


class CloudFront(_AwsComponent):
    """Amazon CloudFront distribution; region is the origin region."""

    service: Literal["cloudfront"]
    edge_geography: Literal[
        "united_states",
        "canada",
        "europe",
        "japan",
        "india",
        "asia_pacific",
        "australia",
        "south_america",
        "middle_east",
        "south_africa",
    ] = Field(description="Where most viewers are; CloudFront prices by edge location.")


class Rds(_AwsComponent):
    """Amazon RDS database instances."""

    service: Literal["rds"]
    engine: Literal["postgres", "mysql", "mariadb"]
    instance_type: str = Field(
        min_length=1, description="RDS instance class, e.g. db.r7g.large."
    )
    multi_az: bool = Field(default=False, description="True for a Multi-AZ deployment.")
    storage_type: Literal["gp3", "gp2", "io2"] = "gp3"
    count: int = Field(default=1, ge=1, description="Number of identical instances.")


class DynamoDb(_AwsComponent):
    """Amazon DynamoDB table(s)."""

    service: Literal["dynamodb"]
    capacity_mode: Literal["on_demand", "provisioned"] = "on_demand"
    table_class: Literal["standard", "standard_ia"] = "standard"


class ElastiCache(_AwsComponent):
    """Amazon ElastiCache nodes."""

    service: Literal["elasticache"]
    engine: Literal["redis", "valkey", "memcached"]
    instance_type: str = Field(
        min_length=1, description="Cache node type, e.g. cache.r7g.large."
    )
    count: int = Field(default=1, ge=1, description="Number of cache nodes.")


class S3(_AwsComponent):
    """Amazon S3 bucket(s)."""

    service: Literal["s3"]
    storage_class: Literal["standard"] = "standard"


class Sqs(_AwsComponent):
    """Amazon SQS queue(s)."""

    service: Literal["sqs"]
    queue_type: Literal["standard", "fifo"] = "standard"


class Sns(_AwsComponent):
    """Amazon SNS topic(s)."""

    service: Literal["sns"]


class CloudWatch(_AwsComponent):
    """Amazon CloudWatch metrics, alarms and logs."""

    service: Literal["cloudwatch"]


class DataTransfer(_AwsComponent):
    """Data leaving `region`: to the internet, to another region, or across AZs."""

    service: Literal["data_transfer"]
    direction: Literal["internet", "inter_region", "cross_az"]
    to_region: AwsRegion | None = Field(
        default=None,
        description="Destination region code; set only when direction is inter_region.",
    )

    @model_validator(mode="after")
    def _to_region_only_for_inter_region(self) -> "DataTransfer":
        if self.direction == "inter_region":
            if self.to_region is None:
                raise ValueError("inter_region data transfer requires to_region")
            if self.to_region == self.region:
                raise ValueError("to_region must differ from region")
        elif self.to_region is not None:
            raise ValueError(
                f"to_region is only used when direction is inter_region, not {self.direction}"
            )
        return self


AWS_COMPONENT_MODELS: tuple[type[_AwsComponent], ...] = (
    Ec2,
    Ebs,
    NatGateway,
    Fargate,
    Eks,
    Lambda,
    ApiGateway,
    LoadBalancer,
    CloudFront,
    Rds,
    DynamoDb,
    ElastiCache,
    S3,
    Sqs,
    Sns,
    CloudWatch,
    DataTransfer,
)
AWS_SERVICES: tuple[str, ...] = tuple(
    get_args(m.model_fields["service"].annotation)[0] for m in AWS_COMPONENT_MODELS
)

AwsComponent = Annotated[
    Ec2
    | Ebs
    | NatGateway
    | Fargate
    | Eks
    | Lambda
    | ApiGateway
    | LoadBalancer
    | CloudFront
    | Rds
    | DynamoDb
    | ElastiCache
    | S3
    | Sqs
    | Sns
    | CloudWatch
    | DataTransfer,
    Field(discriminator="service"),
]


class AwsDesign(BaseModel):
    """Every AWS component chosen for the design, one entry per resource per region."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["aws"] = "aws"
    components: list[AwsComponent] = Field(
        min_length=1,
        description="The chosen components. Multi-region designs list each component once per region.",
    )

    @model_validator(mode="after")
    def _check_unique_ids(self) -> "AwsDesign":
        counts = Counter(c.id for c in self.components)
        duplicates = sorted(i for i, n in counts.items() if n > 1)
        if duplicates:
            raise ValueError(f"duplicate component ids: {', '.join(duplicates)}")
        return self


ComponentChoices = AwsDesign


def unknown_references(design: AwsDesign, spec: RequirementSpec) -> list[str]:
    """Return "component_id: reference" for every based_on entry the spec can't back up.

    - requirement:<field>   must name a field of spec.explicit_requirements that has a
                            value (not null, not an empty list)
    - clarification:<key>   must be a key in spec.clarifications
    - assumption:<key>      must be a key in spec.assumptions
    - sizing:<metric> and kb:<id> are NOT checked yet (no SizingTable or knowledge-base
      index to check against), so they are never reported.
    """
    explicit = spec.explicit_requirements.model_dump()
    known = {
        "requirement": {k for k, v in explicit.items() if v not in (None, [])},
        "clarification": set(spec.clarifications),
        "assumption": set(spec.assumptions),
    }
    unknown = []
    for component in design.components:
        for reference in component.based_on:
            prefix, key = reference.split(":", 1)
            if prefix in known and key not in known[prefix]:
                unknown.append(f"{component.id}: {reference}")
    return unknown
