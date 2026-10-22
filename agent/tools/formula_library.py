def _metric(calc: str, name: str, drives: str) -> dict[str, str]:
    """One row of a system's sizing table: which calculator, what to call it, what it drives."""
    return {"calc": calc, "name": name, "drives": drives}


# Calculators are shared across systems (see capacity_calculator.py); a system only picks
# which ones apply and what to call the result.
PEAK_WRITE_QPS = "calc_peak_write_qps"
PEAK_READ_QPS = "calc_peak_read_qps"
CONNECTIONS = "calc_concurrent_connections"
STORAGE = "calc_storage_growth_yearly"
HOT_SET = "calc_hot_working_set"
EGRESS = "calc_egress_bandwidth"
SESSIONS = "calc_concurrent_sessions"
THROUGHPUT = "calc_network_throughput"
# Little's Law: concurrency = arrival rate x average time in system (e.g. active drivers)
LITTLE = "calc_littles_law_concurrency"

WRITE_DRIVES = "App instance count, DB write capacity, queue throughput"
READ_DRIVES = "Read replica count, cache sizing, CDN strategy"
CONNECTION_DRIVES = "WebSocket gateway fleet size, connection-state store"
STORAGE_DRIVES = "Database tier, object storage class, archival policy"
HOT_SET_DRIVES = "Cache memory sizing (this is what sizes Redis)"
EGRESS_DRIVES = "Data transfer cost, load balancer and CDN capacity"
SESSION_DRIVES = "Streaming/session fleet size, load balancer capacity"
WORKER_DRIVES = "Dispatch service and driver/worker fleet capacity"

FORMULA_LIBRARY = {
    "messaging / chat apps": [
        _metric(PEAK_WRITE_QPS, "peak_write_qps", WRITE_DRIVES),
        _metric(PEAK_READ_QPS, "peak_read_qps", READ_DRIVES),
        _metric(CONNECTIONS, "concurrent_connections", CONNECTION_DRIVES),
        _metric(STORAGE, "storage_growth_per_year", STORAGE_DRIVES),
        _metric(HOT_SET, "hot_working_set", HOT_SET_DRIVES),
        _metric(EGRESS, "egress_bandwidth", EGRESS_DRIVES),
    ],
    "social networks": [
        _metric(PEAK_WRITE_QPS, "feed_updates_qps", WRITE_DRIVES),
        _metric("calc_fanout_load", "fanout_load", "Fan-out workers, timeline cache writes"),
        _metric(PEAK_READ_QPS, "peak_read_qps", READ_DRIVES),
        _metric(CONNECTIONS, "concurrent_connections", CONNECTION_DRIVES),
        _metric(STORAGE, "storage_growth_per_year", STORAGE_DRIVES),
        _metric(HOT_SET, "hot_working_set", HOT_SET_DRIVES),
        _metric(EGRESS, "egress_bandwidth", EGRESS_DRIVES),
    ],
    "video streaming platforms": [
        _metric(SESSIONS, "peak_concurrent_streams", SESSION_DRIVES),
        _metric(THROUGHPUT, "network_throughput", EGRESS_DRIVES),
    ],
    "e-commerce platforms": [
        _metric(PEAK_WRITE_QPS, "orders_per_second", WRITE_DRIVES),
        _metric(PEAK_READ_QPS, "peak_read_qps", READ_DRIVES),
        _metric(STORAGE, "storage_growth_per_year", STORAGE_DRIVES),
        _metric(EGRESS, "egress_bandwidth", EGRESS_DRIVES),
    ],
    "ticket booking systems": [
        _metric(PEAK_WRITE_QPS, "peak_booking_qps", WRITE_DRIVES),
        _metric(PEAK_READ_QPS, "peak_read_qps", READ_DRIVES),
        _metric(STORAGE, "storage_growth_per_year", STORAGE_DRIVES),
    ],
    "food delivery apps": [
        _metric(PEAK_WRITE_QPS, "orders_per_second", WRITE_DRIVES),
        _metric(PEAK_READ_QPS, "peak_read_qps", READ_DRIVES),
        _metric(LITTLE, "driver_concurrency", WORKER_DRIVES),
    ],
    "ride-hailing / mobility apps": [
        _metric(PEAK_WRITE_QPS, "rides_per_second", WRITE_DRIVES),
        _metric(PEAK_READ_QPS, "peak_read_qps", READ_DRIVES),
        _metric(LITTLE, "driver_concurrency", WORKER_DRIVES),
    ],
    "analytics / data warehouse systems": [
        _metric(
            "calc_active_user_query_rate",
            "query_throughput",
            "Warehouse cluster size, concurrency scaling, query queue limits",
        ),
    ],
    "banking / fintech systems": [
        _metric(PEAK_WRITE_QPS, "transactions_per_second", WRITE_DRIVES),
        _metric(PEAK_READ_QPS, "peak_read_qps", READ_DRIVES),
        _metric(STORAGE, "storage_growth_per_year", STORAGE_DRIVES),
    ],
    "education / learning platforms": [
        _metric(SESSIONS, "concurrent_students", SESSION_DRIVES),
    ],
    "search engines / indexing systems": [
        _metric(PEAK_READ_QPS, "search_qps", "Search cluster size, query cache, replica count"),
        _metric(EGRESS, "egress_bandwidth", EGRESS_DRIVES),
    ],
    "content delivery networks (cdn)": [
        _metric(PEAK_READ_QPS, "edge_requests_per_second", "Edge capacity, origin shield sizing"),
        _metric(EGRESS, "egress_bandwidth", EGRESS_DRIVES),
    ],
}

# Every assumption key the calculators read, with its global typical default.
# Single source of truth for the calculator, the RequirementSpec schema and the prompt.
ASSUMPTION_DEFAULTS = {
    # Generic sizing assumptions read by the shared calculators. SYSTEM_ASSUMPTIONS decides,
    # per system type, which of these default to a system value or to a domain key below.
    "writes_per_user_per_day": 50,
    "reads_per_user_per_day": 100,
    "peak_factor": 3,
    "concurrency_ratio": 0.05,
    "avg_item_size_kb": 5,
    "avg_response_size_kb": 50,
    "hot_items_per_user": 100,
    "media_ratio": 0,
    "avg_media_mb": 2,
    "active_hours_per_user_per_day": 2,
    "avg_duration_minutes": 30,
    "ops_per_active_user_per_hour": 2,
    # messaging / chat apps
    "messages_per_user_per_day": 40,
    "avg_message_size_kb": 1,
    # social networks
    "posts_per_user_per_day": 5,
    "avg_followers": 200,
    "feed_reads_per_user_per_day": 50,
    "avg_post_size_kb": 2,
    "timeline_length": 200,
    "avg_feed_response_kb": 100,
    # video streaming platforms
    "average_streaming_hours_per_user_per_day": 2,
    "mbps_per_stream": 3,
    # e-commerce platforms, food delivery apps
    "orders_per_user_per_day": 2,
    # ticket booking systems
    "bookings_per_user_per_day": 3,
    # food delivery apps
    "avg_delivery_time_minutes": 30,
    # ride-hailing / mobility apps
    "rides_per_user_per_day": 2,
    "avg_trip_time_minutes": 20,
    # analytics / data warehouse systems
    "queries_per_user_per_hour": 2,
    # banking / fintech systems
    "transactions_per_user_per_day": 2,
    # education / learning platforms
    "avg_learning_hours_per_user_per_day": 2,
    # search engines / indexing systems
    "queries_per_user_per_day": 10,
    # content delivery networks (cdn)
    "requests_per_user_per_day": 100,
}

# How each system type fills the generic assumptions. A value is one of:
#   number            a fixed system default
#   "domain_key"      take the user's value for that key (or its default)
#   ("domain_key", n) the same, multiplied by n
# A generic key the user supplies directly always wins; a key not listed here falls back
# to its global default in ASSUMPTION_DEFAULTS.
SYSTEM_ASSUMPTIONS = {
    "messaging / chat apps": {
        "writes_per_user_per_day": "messages_per_user_per_day",
        "reads_per_user_per_day": ("messages_per_user_per_day", 50),
        "peak_factor": 3,
        "concurrency_ratio": 0.1,
        "avg_item_size_kb": "avg_message_size_kb",
        "avg_response_size_kb": "avg_message_size_kb",
        "hot_items_per_user": ("messages_per_user_per_day", 3),
    },
    "social networks": {
        "writes_per_user_per_day": "posts_per_user_per_day",
        "reads_per_user_per_day": "feed_reads_per_user_per_day",
        "concurrency_ratio": 0.03,
        "avg_item_size_kb": "avg_post_size_kb",
        "avg_response_size_kb": "avg_feed_response_kb",
        "hot_items_per_user": "timeline_length",
        "media_ratio": 0.2,
        "peak_factor": 3,
    },
    "video streaming platforms": {
        "active_hours_per_user_per_day": "average_streaming_hours_per_user_per_day",
        "peak_factor": 3,
    },
    "e-commerce platforms": {
        "writes_per_user_per_day": "orders_per_user_per_day",
        "reads_per_user_per_day": 30,
        "avg_item_size_kb": 5,
        "avg_response_size_kb": 150,
        "peak_factor": 5,
    },
    "ticket booking systems": {
        "writes_per_user_per_day": "bookings_per_user_per_day",
        "reads_per_user_per_day": 10,
        "avg_item_size_kb": 2,
        "peak_factor": 10,
    },
    "food delivery apps": {
        "writes_per_user_per_day": "orders_per_user_per_day",
        "reads_per_user_per_day": 20,
        "avg_duration_minutes": "avg_delivery_time_minutes",
        "peak_factor": 10,
    },
    "ride-hailing / mobility apps": {
        "writes_per_user_per_day": "rides_per_user_per_day",
        "reads_per_user_per_day": 20,
        "avg_duration_minutes": "avg_trip_time_minutes",
        "peak_factor": 3,
    },
    "analytics / data warehouse systems": {
        "concurrency_ratio": 0.1,
        "ops_per_active_user_per_hour": "queries_per_user_per_hour",
    },
    "banking / fintech systems": {
        "writes_per_user_per_day": "transactions_per_user_per_day",
        "reads_per_user_per_day": 20,
        "avg_item_size_kb": 2,
    },
    "education / learning platforms": {
        "active_hours_per_user_per_day": "avg_learning_hours_per_user_per_day",
    },
    "search engines / indexing systems": {
        "reads_per_user_per_day": "queries_per_user_per_day",
        "avg_response_size_kb": 50,
    },
    "content delivery networks (cdn)": {
        "reads_per_user_per_day": "requests_per_user_per_day",
        "avg_response_size_kb": 200,
    },
}
