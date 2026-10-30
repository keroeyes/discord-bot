"""MCP result compatibility; unknown or malformed flags fail closed."""


def tool_failed(result):
    flags = [getattr(result, name) for name in ("is_error", "isError")
             if hasattr(result, name)]
    return not flags or any(type(flag) is not bool or flag for flag in flags)
