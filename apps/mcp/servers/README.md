# MCP servers

One package per capability in the tool catalog. Block D introduces the first six (booking, queue, client, notification, commission, escalate). Block E adds `agendapro_browser_mcp`.

Each package follows the same shape:

```
servers/<server-name>/
  pyproject.toml
  src/<server_name>/
    __init__.py
    server.py        # MCP entrypoint
    tools.py         # tool implementations
    schemas.py       # Pydantic input/output schemas
    repository.py    # tenant-scoped DB access
  tests/
    test_tools.py
```

`tenant_id` is always derived from the runtime context — never accepted as a tool argument.
