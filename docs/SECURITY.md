# Security Notes

## Tool safety

- Tool names are allowlisted in `SUPPORTED_GEE_OPERATIONS`.
- The graph validates bbox shape and coordinate ranges.
- The graph enforces action count, bbox area, and tile-budget limits.
- The plugin service repeats tile-budget validation server-side.
- No LLM-generated shell, SQL, Python, or filesystem path execution is allowed.

## Container safety

- Production image runs as a non-root user.
- Compose uses `no-new-privileges` for application containers.
- Earth Engine credentials are mounted as Docker secrets.
- Host networking and X11 are removed from the production stack.

## Secrets

Never commit `.env` or `secrets/*.json`. Rotate the default Postgres password before any shared environment.

## MCP caveat

MCP is a useful standardized tool interface, but production safety still requires server-side allowlists, request budgets, structured errors, identity propagation, and audit logs. This overlay treats MCP as an integration protocol, not as a trust boundary.
