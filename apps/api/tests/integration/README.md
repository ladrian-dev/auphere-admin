# Integration tests

Use Testcontainers for Postgres + Redis. Slower than unit tests; not run on every push.

```bash
cd apps/api
uv run pytest tests/integration/ -v
```

Block B will introduce the first integration tests around the data model.
