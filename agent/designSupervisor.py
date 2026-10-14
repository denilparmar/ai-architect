import atexit
import json
import re

from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from agent.factory import build_capacity_agent, build_req_agent
from observability.logger import get_logger

logger = get_logger(__name__)
_agent = None
_memory = None
_database = None
# Max graph steps per agent run (each resume after a question is a new run).
REQUIREMENTS_RECURSION_LIMIT = 25


def _close_database() -> None:
    if _database:
        _database.close()


atexit.register(_close_database)


def handle_query(question: str, thread_id: str) -> str:
    """Entry point for all user queries - reuses the agent and runs it."""
    global _agent, _memory, _database
    logger.info("Handling query for session %s", thread_id)
    try:
        if _agent is None:
            _agent, _memory, _database = build_req_agent()
        agent_config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": REQUIREMENTS_RECURSION_LIMIT,
        }
        try:
            response = _agent.invoke(
                {"messages": [{"role": "user", "content": question}]},
                agent_config,
            )
            result = _handle_interrupts(_agent, response, agent_config)
        except GraphRecursionError as e:
            raise RuntimeError(
                "requirements agent couldn't produce a valid spec after "
                f"{REQUIREMENTS_RECURSION_LIMIT} steps"
            ) from e
        spec = result.get("structured_response")
        if spec is None:
            raise RuntimeError("requirements agent finished without a structured spec")
        requirement_spec = spec.model_dump(mode="json")
        print("\nFinal Structured Requirement Spec (JSON):")
        print(spec.model_dump_json(indent=2))
        _database.save_requirement_specs(thread_id, requirement_spec)

        # Call the capacity agent, which generates and saves sizing specs.
        invoke_capacity_agent(requirement_spec, thread_id)

        sizing_spec_data = _database.get_sizing_specs(thread_id)
        print("\nPrinting the sizing_spec_data now:")
        print(sizing_spec_data)

        # call to component selection agent
        # handle_component_selection(requirement_spec,sizing_spec_data)

        # call to cost estimation agent

        # call to architecture composer agent (include design critic agent to verify)
        logger.info("Successfully handled query for session %s", thread_id)
        return spec.model_dump_json(indent=2)
    except Exception:
        logger.exception("Failed to handle query for session %s", thread_id)
        raise


def invoke_capacity_agent(requirement_spec, thread_id):
    """Invoke the capacity agent to calculate sizing specs based on the requirement spec."""
    """."""
    capAgent = build_capacity_agent(requirement_spec)
    capacity_results = capAgent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Calculate capacity based on the requirement spec.",
                }
            ]
        }
    )
    print("\nCapacity Calculation Results (JSON):")
    final_ai_message = capacity_results["messages"][-1]
    print(final_ai_message.content)
    # Extract content between ```json ... ```
    match = re.search(r"```json\s*(.*?)\s*```", final_ai_message.content, re.DOTALL)
    print("match object:", match)
    if match:
        json_str = match.group(1)
        capacity_data = json.loads(json_str)
        print("\nParsed Capacity Data (JSON):")
        print(capacity_data)
    # Save capacity specs to the database
    _database.save_sizing_specs(thread_id, capacity_data)


def _handle_interrupts(agent, result, config: dict) -> dict:
    """Collect clarification answers and resume human-in-the-loop tool calls."""
    while result.get("__interrupt__"):
        interrupt = result["__interrupt__"][0]
        interrupt_data = interrupt.value
        logger.info(f"Handling interrupt: {interrupt_data}")

        action_requests = interrupt_data.get("action_requests", [])
        if not action_requests:
            logger.warning("Interrupt did not contain any action requests")
            break

        decisions = []
        for action_request in action_requests:
            question = (
                action_request["args"].get("question") or action_request["description"]
            )
            user_input = ""
            while not user_input:
                user_input = input(f"[HITL] {question} ").strip()
                if not user_input:
                    logger.info("Empty clarification response; asking again")
            decisions.append({"type": "respond", "message": user_input})

        result = agent.invoke(Command(resume={"decisions": decisions}), config)
    return result


# def flatten_requirement_spec(requirement_spec):
#     if isinstance(requirement_spec, str):
#         try:
#             requirement_spec = json.loads(requirement_spec)
#         except json.JSONDecodeError:
#             return requirement_spec

#     parts = []

#     system_type = requirement_spec.get("system_type")
#     if system_type:
#         parts.append(str(system_type))

#     explicit = requirement_spec.get("explicit_requirements", {})
#     if isinstance(explicit, dict):
#         for key, value in explicit.items():
#             parts.append(f"{key.replace('_', ' ')}: {value}")

#     clarifications = requirement_spec.get("clarifications", {})
#     if isinstance(clarifications, dict):
#         for key, value in clarifications.items():
#             parts.append(f"{key.replace('_', ' ')}: {value}")

#     assumptions = requirement_spec.get("assumptions", {})
#     if isinstance(assumptions, dict):
#         for key, value in assumptions.items():
#             parts.append(f"{key.replace('_', ' ')}: {value}")

#     return ". ".join(parts)

# def build_hybrid_query(requirement_spec, sizing_spec_data):
#     """Build semantic + lexical query strings from requirement and sizing data."""
#     if isinstance(requirement_spec, str):
#         try:
#             requirement_obj = json.loads(requirement_spec)
#         except json.JSONDecodeError:
#             requirement_obj = {"system_type": requirement_spec}
#     else:
#         requirement_obj = requirement_spec or {}

#     sizing_rows = sizing_spec_data or []
#     constraint_text = []
#     for row in sizing_rows:
#         category = row.get("resource_category", "")
#         requirement = row.get("requirement", "")
#         if category and requirement:
#             constraint_text.append(f"{category}: {requirement}")

#     system_type = requirement_obj.get("system_type", "distributed system")
#     req_summary = flatten_requirement_spec(requirement_obj)
#     semantic_query = (
#     f"{system_type} workload with requirements {req_summary} "
#     f"and constraints {'; '.join(constraint_text) if constraint_text else 'managed service, low latency, scalable'}"
#     )

#     lexical_tokens = [
#         system_type,
#         *constraint_text,
#     ]
#     lexical_query = " ".join(filter(None, lexical_tokens))

#     numeric_filters = {
#         "managed_service_only": True,
#     }
#     for row in sizing_rows:
#         key = str(row.get("resource_category", "")).lower()
#         value = str(row.get("requirement", ""))
#         if "latency" in key:
#             try:
#                 numeric_filters["max_latency_ms"] = float(value.split("<")[-1].split("ms")[0].strip())
#             except ValueError:
#                 pass
#         if "write" in key and "throughput" in key.lower():
#             try:
#                 numeric_filters["min_write_throughput"] = float(value.split(" ")[0])
#             except ValueError:
#                 pass

#     return {
#         "semantic": semantic_query,
#         "lexical": lexical_query,
#         "numeric_filters": numeric_filters,
#     }


# def apply_numeric_filters(results, filters):
#     """Filter results by region, latency, and throughput constraints."""
#     if not isinstance(results, list):
#         return []

#     filtered = []
#     for item in results:
#         item = item or {}
#         metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
#         text = item.get("content") or item.get("snippet") or item.get("title") or ""
#         region_ok = True
#         if filters.get("region"):
#             region_ok = filters["region"] in str(metadata.get("regions", "") + " " + text)

#         managed_ok = True
#         if filters.get("managed_service_only"):
#             managed_ok = "managed" in str(text).lower() or metadata.get("managed") is True

#         latency_ok = True
#         if filters.get("max_latency_ms") is not None:
#             latency_value = metadata.get("latency_ms")
#             if latency_value is None:
#                 latency_ok = "latency" not in str(text).lower() or "<" in str(text).lower()
#             else:
#                 latency_ok = float(latency_value) <= float(filters["max_latency_ms"])

#         throughput_ok = True
#         if filters.get("min_write_throughput") is not None:
#             throughput_value = metadata.get("write_throughput")
#             if throughput_value is None:
#                 throughput_ok = "write" not in str(text).lower() or "throughput" in str(text).lower()
#             else:
#                 throughput_ok = float(throughput_value) >= float(filters["min_write_throughput"])

#         if region_ok and managed_ok and latency_ok and throughput_ok:
#             filtered.append(item)

#     return filtered


# def reciprocal_rank_fusion(semantic_results, lexical_results, k=60):
#     """Merge semantic and lexical result lists by rank."""
#     ranked = {}
#     for results, weight in [(semantic_results, 1.0), (lexical_results, 1.0)]:
#         for rank, item in enumerate(results or []):
#             key = item.get("id") or item.get("url") or item.get("title") or str(rank)
#             ranked[key] = ranked.get(key, 0.0) + weight * (1.0 / (k + rank))
#     return [
#         {"key": key, "score": score}
#         for key, score in sorted(ranked.items(), key=lambda pair: pair[1], reverse=True)
#     ]


# def _limit_results_to_services(results, services):
#     """Filter search results to only docs whose text mentions the selected AWS services."""
#     if not results or not services:
#         return results

#     service_names = [str(s).strip().lower() for s in services if str(s).strip()]
#     if not service_names:
#         return results

#     filtered = []
#     for item in results:
#         if not isinstance(item, dict):
#             continue
#         text = str(item.get("content") or item.get("snippet") or item.get("title") or "")
#         metadata = item.get("metadata", {}) or {}
#         combined = " ".join(
#             [
#                 text,
#                 str(metadata.get("title", "")),
#                 str(metadata.get("service", "")),
#                 str(metadata.get("service_name", "")),
#             ]
#         ).lower()
#         if any(service in combined for service in service_names):
#             filtered.append(item)
#     return filtered


# def hybrid_retrieve(requirement_spec, sizing_spec_data, mcp: MCPClient, mapping: dict | None = None):
#     """Retrieve semantically and lexically relevant AWS docs and merge them."""
#     query = build_hybrid_query(requirement_spec, sizing_spec_data)
#     selected_services = []
#     if isinstance(mapping, dict):
#         selected_services = [str(s).strip() for s in mapping.get("services", []) if str(s).strip()]

#     if selected_services:
#         query["semantic"] = f"{' '.join(selected_services)} {query['semantic']}"
#         query["lexical"] = " ".join(filter(None, [*selected_services, query["lexical"]]))

#     semantic_results = mcp.search_docs(query=query["semantic"])
#     lexical_results = mcp.search_docs(query=query["lexical"])

#     if selected_services:
#         semantic_results = _limit_results_to_services(semantic_results, selected_services)
#         lexical_results = _limit_results_to_services(lexical_results, selected_services)

#     fused = reciprocal_rank_fusion(semantic_results, lexical_results)
#     filtered = apply_numeric_filters(semantic_results + lexical_results, query["numeric_filters"])
#     # reranking the results
#     return {
#         "query": query,
#         "fused": fused,
#         "filtered": filtered,
#     }


# def handle_component_selection(requirement_spec, sizing_spec_data) -> dict:
#     # Requirement spec → tells you what kind of workload you’re designing for.
#     # Sizing specs → tells you what quantitative constraints must be satisfied.
#     awsMcp = MCPClient(region="us-east-1")
#     mapping = decide_services(requirement_spec, sizing_spec_data)
#     hybrid_result = hybrid_retrieve(requirement_spec, sizing_spec_data, awsMcp, mapping)
#     result = collect_corpus(mapping, awsMcp)
#     final = {
#         "selected_services": mapping,
#         "hybrid_retrieval": hybrid_result,
#         "docs": result["docs"],
#         "quotas": result["quotas"],
#     }
#     print(json.dumps(final, indent=2, default=str))
#     return final


# def decide_services(requirement_spec, sizing_specs):
#     small_llm = get_small_llm()
#     # Build the prompt dynamically
#     prompt = f"""
#     You are a helper that maps workload requirements to AWS services and quota codes.

#     Requirement spec:
#     {requirement_spec}

#     Sizing specs:
#     {sizing_specs}

#     Task: Return a JSON object with keys "services" and "quotas".
#     Example:
#     {"services": ["dynamodb", "elasticache"], "quotas": [{"service_code": "dynamodb", "quota_code": "WriteCapacityUnits"}]}
#     """
#     result = small_llm.invoke(prompt)
#     text = result.content
#     print(f"\nLLM raw response:\n{text}")
#     parsed = json.loads(text)
#     print(f"\nList of AWS services and Quota codes (JSON): {parsed}")
#     return parsed


# def collect_corpus(mapping: dict, mcp: MCPClient) -> dict:
#     quota_client = boto3.client("service-quotas", region_name="us-east-1")
#     docs = []
#     quotas = []

#     for svc in mapping.get("services", []):
#         try:
#             svc_docs = mcp.search_docs(query=f"{svc} AWS documentation")
#             docs.extend(svc_docs)
#         except Exception as e:
#             logger.warning(f"Could not fetch docs for service {svc}: {e}")

#     for quota in mapping.get("quotas", []):
#         try:
#             resp = quota_client.get_service_quota(
#                 ServiceCode=quota["service_code"],
#                 QuotaCode=quota["quota_code"],
#             )
#             quotas.append(resp)
#         except Exception as e:
#             logger.warning(
#                 f"Could not fetch quota for {quota.get('service_code')} / "
#                 f"{quota.get('quota_code')}: {e}"
#             )

#     return {"docs": docs, "quotas": quotas}
