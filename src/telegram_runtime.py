def calculate_telegram_request_limit(
    current_subbot_count: int,
    max_subbot_count: int,
    configured_limit: int,
    connections_per_bot: int = 4,
    overhead_connections: int = 20,
) -> int:
    target_subbot_count = max(current_subbot_count, max_subbot_count, 0)
    active_bot_count = target_subbot_count + 1
    required_limit = active_bot_count * connections_per_bot + overhead_connections
    return max(configured_limit, required_limit)
