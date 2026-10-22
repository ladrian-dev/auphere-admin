# Bug Fix: la pestaña de auditoría del partner da 500

- **Slug**: auditoria-del-partner-500
- **Fixed**: 2026-10-22
- **Assessment**: ./assessment.md
- **Status**: applied (rama `hotfix/prod-2026-10-22`, sin desplegar)

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/schemas/partner.py` | modified | `_ip_as_text`: `None` o `str(v)` |
| `apps/api/tests/unit/test_partner_audit_ip.py` | new test | IPv4, IPv6, con máscara, texto y `None` |
