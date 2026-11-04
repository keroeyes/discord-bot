"""MCP result compatibility; unknown or malformed flags fail closed."""
import json


def tool_failed(result):
    flags = [getattr(result, name) for name in ("is_error", "isError")
             if hasattr(result, name)]
    return not flags or any(type(flag) is not bool or flag for flag in flags)


def query_failure(name, result):
    """Validate the pinned Serena 2.1 JSON contract without logging source text."""
    if tool_failed(result):
        return "tool_error"
    content = getattr(result, "content", None)
    if not isinstance(content, list) or len(content) != 1:
        return "invalid_result"
    block = content[0]
    text = getattr(block, "text", None)
    if (getattr(block, "type", None) != "text" or not isinstance(text, str)
            or len(text) > 262144):
        return "invalid_result"
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        return "invalid_result"
    if not isinstance(payload, dict):
        return "invalid_result"
    if name == "get_symbols_overview":
        functions = payload.get("Function")
        if isinstance(functions, list) and "main" in functions:
            return None
        return "expected_symbol_missing"
    if name == "find_referencing_symbols":
        groups = payload.get("main.py")
        methods = groups.get("Method") if isinstance(groups, dict) else None
        if isinstance(methods, list) and any(
            isinstance(item, dict) and item.get("name_path") == "Bot/on_message"
            for item in methods
        ):
            return None
        return "expected_reference_missing"
    return "unsupported_query"
