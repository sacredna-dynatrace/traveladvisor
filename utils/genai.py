from opentelemetry import trace


def mark_tool_span(name: str, description: str) -> None:
    """Add OpenTelemetry GenAI tool attributes (execute_tool) to the current tool span
    created by the LangChain instrumentation, so Dynatrace can show agent tool calls."""
    span = trace.get_current_span()
    span.set_attribute("gen_ai.operation.name", "execute_tool")
    span.set_attribute("gen_ai.tool.name", name)
    span.set_attribute("gen_ai.tool.type", "function")
    span.set_attribute("gen_ai.tool.description", description)
