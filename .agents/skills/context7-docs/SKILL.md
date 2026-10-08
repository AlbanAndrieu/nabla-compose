---
name: context7-docs
description: Resolve current, version-specific external library documentation with Context7 while keeping repository/runtime evidence authoritative.
---

# Context7 documentation lookup

Use this skill only when an implementation decision depends on the current API,
configuration or version-specific behavior of an external library/tool. Typical
examples are Dagger, Docker/Compose, Kubernetes/Talos and Python/JavaScript
libraries.

Do not use Context7 to infer repository state, deployed versions, TrueNAS state,
secret values or runtime health. Inspect repository files/lockfiles and runtime
evidence for those facts.

OpenCode V2 consumes the repository entry from
`opencode.json -> mcp.servers.context7` with Code Mode enabled. The generic
`.mcp.json` and Cursor configuration remain adapters for their own clients;
do not assume they configure OpenCode.

## Free-first policy

Use the cheapest supported access path:

1. Prefer the repository Context7 MCP entry at
   `https://mcp.context7.com/mcp`. It is intentionally configured without
   headers/API keys so supported clients use anonymous/free access.
2. If MCP is unavailable, use the CLI without login/API key. Disable anonymous
   telemetry for repository work:

   ```bash
   CTX7_TELEMETRY_DISABLED=1 npx -y ctx7 library <library> "<specific question>" --json
   CTX7_TELEMETRY_DISABLED=1 npx -y ctx7 docs /org/project[/version] "<specific question>"
   ```

3. If the anonymous quota is insufficient, prefer the provider's free login/OAuth
   path before considering any paid tier.
4. `CONTEXT7_API_KEY` is optional and reserved for non-interactive automation
   or higher free-plan limits. Never require it for normal agent operation and
   never commit it.

## Query discipline

- Resolve the library name first; `ctx7 docs` requires a full Context7 library
  ID such as `/org/project`.
- Prefer an exact version-specific ID when the task depends on a pinned version.
- Ask a concrete implementation question rather than a broad keyword.
- Prefer high-reputation/current documentation results when several libraries
  match.
- Do not send secrets, private runtime payloads or confidential evidence in a
  Context7 query.
- Treat retrieved examples as external documentation, not as proof that the
  repository or runtime already follows them.

## Fallback

If Context7 has no suitable library/version, is rate-limited, or cannot answer
the question, use the upstream official documentation/release notes directly.
Do not block local-first work merely because Context7 is unavailable.

For repository behavior, local tests/contracts remain authoritative. For live
homelab behavior, use the appropriate runtime skill/diagnostic instead.
