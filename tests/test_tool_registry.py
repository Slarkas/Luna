"""Unit tests for Luna's ToolRegistry."""

import pytest

from app.tools.registry import ToolRegistry


def test_registry_empty_init() -> None:
    """An empty registry has no tools."""
    registry = ToolRegistry()
    assert registry.list_tools() == {}


def test_register_and_list() -> None:
    """Register a tool and verify it appears in the list."""
    registry = ToolRegistry()

    def dummy_func(greeting: str, name: str = "World") -> str:
        return f"{greeting}, {name}!"

    registry.register(
        name="greet",
        description="Greets a person",
        callable=dummy_func,
        parameters={"greeting": {"type": "string"}, "name": {"type": "string", "default": "World"}},
    )

    tools = registry.list_tools()
    assert "greet" in tools
    assert tools["greet"]["description"] == "Greets a person"


def test_duplicate_registration_rejected() -> None:
    """Registering the same name twice raises ValueError."""
    registry = ToolRegistry()

    def func1() -> None:
        pass

    def func2() -> None:
        pass

    registry.register(name="dup", description="first", callable=func1, parameters={})

    with pytest.raises(ValueError, match="Tool 'dup' is already registered"):
        registry.register(name="dup", description="second", callable=func2, parameters={})


def test_execute_registered_tool() -> None:
    """Execute a registered tool by name with keyword arguments."""
    registry = ToolRegistry()

    def dummy_func(greeting: str, name: str = "World") -> str:
        return f"{greeting}, {name}!"

    registry.register(
        name="greet",
        description="Greets a person",
        callable=dummy_func,
        parameters={"greeting": {"type": "string"}, "name": {"type": "string", "default": "World"}},
    )

    result = registry.execute("greet", greeting="Hello", name="Alice")
    assert result == "Hello, Alice!"


def test_execute_unknown_tool_raises_keyerror() -> None:
    """Executing a tool that is not registered raises KeyError."""
    registry = ToolRegistry()

    with pytest.raises(KeyError, match="Tool 'nonexistent' is not registered"):
        registry.execute("nonexistent")


def test_execute_without_registering_first() -> None:
    """Execute a tool without registering it first raises KeyError."""
    registry = ToolRegistry()

    with pytest.raises(KeyError):
        registry.execute("greet")


def test_weather_tool_registered() -> None:
    """The get_weather tool is registered through the helper."""
    from app.tools.registry import _tool_registry, register_weather_tool

    # register_weather_tool may have already been called at import time,
    # so just verify the registry has the tool
    tools = _tool_registry.list_tools()
    assert "get_weather" in tools
    assert tools["get_weather"]["description"] == "Get current weather for a city using Open-Meteo API"


def test_weather_tool_execution() -> None:
    """Execute the registered get_weather tool (will fail without network, but checks registry)."""
    from app.tools.registry import _tool_registry

    tools = _tool_registry.list_tools()
    assert "get_weather" in tools
    # The tool is registered; executing it requires network access.
    # We just verify the registry state is correct here.
    assert tools["get_weather"]["callable"] is not None


def test_invalid_arguments_propagated() -> None:
    """Invalid arguments passed to a tool propagate from the callable."""
    registry = ToolRegistry()

    def needs_two_ints(x: int, y: int) -> int:
        return x + y

    registry.register(
        name="add",
        description="Adds two integers",
        callable=needs_two_ints,
        parameters={"x": {"type": "int"}, "y": {"type": "int"}},
    )

    # Passing wrong types will cause a TypeError from the callable
    with pytest.raises(TypeError):
        registry.execute("add", x="not_an_int", y=1)  # type: ignore[arg-type]


def test_get_tool_schemas_empty() -> None:
    """An empty registry produces no schemas."""
    registry = ToolRegistry()
    assert registry.get_tool_schemas() == []


def test_get_tool_schemas_structure() -> None:
    """Each schema is an OpenAI function-tool definition."""
    registry = ToolRegistry()

    def dummy_func(greeting: str) -> str:
        return greeting

    registry.register(
        name="greet",
        description="Greets a person",
        callable=dummy_func,
        parameters={"greeting": {"type": "string"}},
    )

    schemas = registry.get_tool_schemas()
    assert len(schemas) == 1
    schema = schemas[0]
    assert schema == {
        "type": "function",
        "function": {
            "name": "greet",
            "description": "Greets a person",
            "parameters": {
                "type": "object",
                "properties": {"greeting": {"type": "string"}},
                "required": ["greeting"],
                "additionalProperties": False,
            },
        },
    }


def test_get_tool_schemas_required_parameters() -> None:
    """Parameters without a default are required; ones with a default are not."""
    registry = ToolRegistry()

    def dummy_func(greeting: str, name: str = "World") -> str:
        return f"{greeting}, {name}!"

    registry.register(
        name="greet",
        description="Greets a person",
        callable=dummy_func,
        parameters={
            "greeting": {"type": "string"},
            "name": {"type": "string", "default": "World"},
        },
    )

    schemas = registry.get_tool_schemas()
    assert schemas[0]["function"]["parameters"]["required"] == ["greeting"]


def test_get_tool_schemas_get_weather_requires_city() -> None:
    """The registered get_weather tool requires a string city parameter."""
    from app.tools.registry import _tool_registry

    schemas = _tool_registry.get_tool_schemas()
    weather = next(s for s in schemas if s["function"]["name"] == "get_weather")
    params = weather["function"]["parameters"]
    assert params["type"] == "object"
    assert params["properties"]["city"] == {"type": "string"}
    assert params["required"] == ["city"]
    assert params["additionalProperties"] is False


def test_get_tool_schemas_multiple_tools() -> None:
    """Schemas are produced for every registered tool."""
    registry = ToolRegistry()

    def func_a() -> None:
        pass

    def func_b() -> None:
        pass

    registry.register(name="a", description="tool a", callable=func_a, parameters={})
    registry.register(name="b", description="tool b", callable=func_b, parameters={})

    schemas = registry.get_tool_schemas()
    assert len(schemas) == 2
    assert [s["function"]["name"] for s in schemas] == ["a", "b"]


def test_get_tool_schemas_does_not_execute_tools() -> None:
    """Generating schemas never calls a tool's callable."""
    registry = ToolRegistry()

    def boom() -> None:
        raise RuntimeError("callable must not be invoked during schema generation")

    registry.register(
        name="boom", description="explodes", callable=boom, parameters={}
    )

    # Should not raise: the callable is never executed.
    schemas = registry.get_tool_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "boom"