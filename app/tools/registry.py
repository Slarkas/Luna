"""Minimal tool registry for Luna.

Allows registering approved tools by name and executing them with
keyword arguments. Uses only Python standard library.
"""

from typing import Any, Callable


class ToolRegistry:
    """Registry for approved tools with name-based execution.

    Tools are registered with a unique name, description, callable, and
    parameter specification. Duplicate registrations are rejected.
    """

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, name: str, description: str, callable: Callable, parameters: dict[str, Any]) -> None:
        """Register a tool with the registry.

        Args:
            name: Unique tool name.
            description: Human-readable description.
            callable: The function to execute.
            parameters: Parameter specification dict.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = {
            "name": name,
            "description": description,
            "callable": callable,
            "parameters": parameters,
        }

    def list_tools(self) -> dict[str, dict[str, Any]]:
        """Return a copy of the registered tools metadata.

        Returns:
            Dict mapping tool names to their metadata dicts.
        """
        return self._tools.copy()

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible function-tool definitions for registered tools.

        Each schema advertises a tool's name, description, and parameter JSON
        schema so an OpenAI-compatible LLM can request tool calls. Tools are
        not executed while generating schemas.

        Returns:
            A list of ``{"type": "function", "function": {...}}`` dicts, one
            per registered tool.
        """
        schemas: list[dict[str, Any]] = []
        for name, tool in self._tools.items():
            parameters = tool["parameters"]
            properties: dict[str, Any] = {}
            required: list[str] = []
            for param_name, param_spec in parameters.items():
                properties[param_name] = dict(param_spec)
                if "default" not in param_spec:
                    required.append(param_name)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool["description"],
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        },
                    },
                }
            )
        return schemas

    def execute(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a registered tool by name with the given arguments.

        Args:
            tool_name: The tool name to execute.
            **kwargs: Keyword arguments to pass to the tool's callable.

        Returns:
            The result of the callable.

        Raises:
            KeyError: If the tool name is not registered.
            TypeError: If the callable raises a TypeError (e.g., invalid arguments).
        """
        if tool_name not in self._tools:
            raise KeyError(f"Tool '{tool_name}' is not registered")
        tool = self._tools[tool_name]
        callable = tool["callable"]
        return callable(**kwargs)


# Global registry instance for Luna's approved tools
_tool_registry = ToolRegistry()


def get_weather(city: str) -> dict:
    """Get current weather for a city.

    This is the explicitly registered weather tool.
    """
    from app.tools.weather import WeatherClient

    client = WeatherClient(timeout=10)
    return client.get_weather(city)


def register_weather_tool(registry: ToolRegistry) -> None:
    """Register the WeatherClient.get_weather as the ``get_weather`` tool.

    Args:
        registry: The ``ToolRegistry`` instance to register with.
    """
    registry.register(
        name="get_weather",
        description="Get current weather for a city using Open-Meteo API",
        callable=get_weather,
        parameters={"city": {"type": "string"}},
    )


# Auto-register the weather tool when this module is imported
register_weather_tool(_tool_registry)