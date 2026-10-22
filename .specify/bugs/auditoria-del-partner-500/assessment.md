# Bug Assessment: la pestaña de auditoría del partner da 500

- **Slug**: auditoria-del-partner-500
- **Created**: 2026-10-22
- **Source**: logs de `/nexus/prod/api`, 2026-10-22 10:50:12 UTC
- **Verdict**: valid
- **Severity**: low — solo el Admin; ningún cliente lo ve

## Symptom

`GET /admin/partners/7b23b03f-…/audit?limit=100` → 500:

```
ValidationError: 1 validation error for EmbedAuditEntryOut
ip  Input should be a valid string [input_value=IPv4Address('10.40.7.158')]
```

## Root cause

`embed_audit_log.ip` es `INET`; asyncpg lo devuelve como `ipaddress.IPv4Address`
y `EmbedAuditEntryOut.ip` está declarado `str`. Basta una fila con IP para que
caiga la lista entera.

## Suspected Code Paths

- `apps/api/src/nexus_api/schemas/partner.py` — `EmbedAuditEntryOut`.

## Possible Remediation

Validador `mode="before"` que pase la IP a texto.
