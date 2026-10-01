---
name: agentgateway-integration
description: Integrate agentgateway (open-source A2A + MCP proxy) into a multi-agent stack. Use when setting up agentgateway alongside LangChain/LangGraph A2A agents, registering MCP servers, writing config.yaml, running with Docker Compose, or deploying to Kubernetes/GKE. Covers installation, full config reference, Virtual MCP federation, A2A agent routing, RBAC/Cedar policies, OTel observability, and Docker/K8s deployment.
license: MIT
compatibility: Requires Docker, Docker Compose, and/or Kubernetes (GKE). Binary install requires Linux/macOS. Python agents require a2a-sdk. Agentgateway binary available via curl installer or cr.agentgateway.dev/agentgateway Docker image.
metadata:
  author: rudolf-luttich
  version: "1.1"
  agentgateway-version: v1.3.0-alpha.1
  sources: https://agentgateway.dev, https://github.com/agentgateway/agentgateway
allowed-tools: Bash Read
---

# AgentGateway Integration

AgentGateway is an open-source Rust-based proxy that unifies A2A agent traffic, MCP tool servers, and LLM routing behind a single gateway — with built-in RBAC (Cedar policies), OpenTelemetry observability, and a local admin UI.

See [detailed reference guide](references/REFERENCE.md) for full config schema, Kubernetes manifests, and LangGraph A2A wiring.

---

## Architecture

```
Your Agents (LangGraph / A2A Client / MCP Client)
        │  HTTP
        ▼
  agentgateway  (port 3000 + admin :15000)
   ├── A2A routes  → Cedar RBAC → OTel → Agent A, Agent B ...
   └── MCP routes  → Cedar RBAC → OTel → MCP Srv A, MCP Srv B ...
```

---

## 1. Installation

### Binary

```bash
curl -sL https://agentgateway.dev/install | bash
agentgateway --version
```

### Docker image

```
cr.agentgateway.dev/agentgateway:v1.3.0-alpha.1
```

---

## 2. Configuration File Structure

AgentGateway is driven entirely by a YAML (or JSON) config file.

| Section | Purpose |
|---------|---------|
| `config` | Static top-level settings (not hot-reloaded) |
| `binds` | Full routing model — listeners → routes → backends |
| `mcp` | Simplified shorthand for MCP-only setups |
| `llm` | Simplified shorthand for LLM routing |

`binds` is preferred for combined A2A + MCP stacks.

### Config skeleton

```yaml
# yaml-language-server: $schema=https://agentgateway.dev/schema/config
binds:
  - port: 3000
    listeners:
      - routes:
          - policies:
              cors:
                allowOrigins: ["*"]
                allowHeaders: [content-type, cache-control, mcp-protocol-version, mcp-session-id]
                exposeHeaders: ["Mcp-Session-Id"]
            backends:
              - <backend definition>
```

Config is **hot-reloaded** on file save for everything except the `config` block.

---

## 3. Registering MCP Servers

### Simplified (single/few servers)

```yaml
mcp:
  port: 3000
  targets:
    - name: my-tool-server        # stdio local process
      stdio:
        cmd: python
        args: ["-m", "my_mcp_server"]

    - name: remote-tool-server    # HTTP / Streamable-HTTP
      mcp:
        host: http://localhost:8080/mcp
```

### Full `binds` format (federation / RBAC)

```yaml
binds:
  - port: 3001
    listeners:
      - routes:
          - policies:
              cors:
                allowOrigins: ["*"]
                allowHeaders: [content-type, cache-control, mcp-protocol-version, mcp-session-id]
                exposeHeaders: ["Mcp-Session-Id"]
            backends:
              - mcp:
                  targets:
                    - name: filesystem-tools
                      stdio:
                        cmd: npx
                        args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
                    - name: web-search-tools
                      mcp:
                        host: http://mcp-search:8080/mcp
                    - name: db-tools
                      mcp:
                        host: http://mcp-db:8081/mcp
```

Multiple targets under one backend = **Virtual MCP federation** — all tools aggregated behind one endpoint.

---

## 4. Plugging In A2A Agents

Each A2A agent must expose:
- `GET /.well-known/agent-card.json` — Agent Card (a2a-sdk default; older builds used `/.well-known/agent.json`)
- `POST /` — JSON-RPC 2.0 A2A endpoint (`message/send`, `tasks/get`)

> **⚠️ Route schema (verified against v1.3.0-alpha.1).** In the `binds` route model, a route's
> match key is **`matches:`** (a list of `{ path: { pathPrefix | exact | regex } }`), and **`a2a`
> is a route _policy_** — `policies: { a2a: {} }` — **not** a route-level sibling. A `pathPrefix`
> match does **not** strip the prefix, so for path-based routing add a `urlRewrite` to forward the
> backend's expected path. Validate any config without booting the stack:
> `agentgateway -f config.yaml --validate-only` (or via the Docker image:
> `docker run --rm -v "$PWD/config.yaml:/config.yaml:ro" cr.agentgateway.dev/agentgateway:v1.3.0-alpha.1 -f /config.yaml --validate-only`).

### Single agent (no path prefix → no rewrite needed)

```yaml
binds:
  - port: 3000
    listeners:
      - routes:
          - policies:
              a2a: {}
            backends:
              - host: my-langgraph-agent:9999
```

### Multiple agents (path-based routing)

Each route matches a `/agent/<name>` prefix and strips it (`urlRewrite`) so the backend receives
`/` (where its Agent Card and JSON-RPC endpoint live):

```yaml
binds:
  - port: 3000
    listeners:
      - routes:
          - matches:
              - path:
                  pathPrefix: /agent/orchestrator
            policies:
              a2a: {}
              urlRewrite:
                path:
                  prefix: /
            backends:
              - host: orchestrator-agent:9001

          - matches:
              - path:
                  pathPrefix: /agent/researcher
            policies:
              a2a: {}
              urlRewrite:
                path:
                  prefix: /
            backends:
              - host: researcher-agent:9002
          # …one route per agent
```

> **Client gotcha:** a resolved Agent Card advertises the *agent's own* URL, so an A2A client that
> honours `card.url` will bypass the gateway on `message/send`. Either have the client override
> `card.url` with the gateway route, or rely on the `a2a` policy's card-URL rewrite — confirm which
> your version does. (agentgateway v1.3.0-alpha.1 rewrites the proxied card's `url` to the gateway.)

### Combined A2A + MCP (multi-port)

```yaml
binds:
  - port: 3000          # A2A traffic
    listeners:
      - routes:
          - policies:
              a2a: {}
            backends:
              - host: orchestrator-agent:9999

  - port: 3001          # MCP traffic (Virtual MCP federation)
    listeners:
      - routes:
          - matches:
              - path:
                  pathPrefix: /mcp
            backends:
              - mcp:
                  targets:
                    - name: tools-server
                      mcp:
                        host: http://mcp-tools:8080/mcp
```

---

## 5. Docker Compose

```yaml
# docker-compose.yml
services:

  agentgateway:
    container_name: agentgateway
    image: cr.agentgateway.dev/agentgateway:v1.3.0-alpha.1
    restart: unless-stopped
    ports:
      - "3000:3000"
      - "3001:3001"
      - "127.0.0.1:15000:15000"   # Admin UI — localhost only
    volumes:
      - ./config.yaml:/config.yaml
    environment:
      - ADMIN_ADDR=0.0.0.0:15000  # Required to expose admin UI from container
    command: ["-f", "/config.yaml"]
    depends_on:
      - orchestrator-agent
      - mcp-tools

  orchestrator-agent:
    build: ./agents/orchestrator
    ports:
      - "9999:9999"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

  mcp-tools:
    build: ./mcp/tools-server
    ports:
      - "8080:8080"
```

> **Important**: In Docker Compose, use **service names** as hostnames in `config.yaml` — never `localhost`.

### Run

```bash
docker compose up -d
docker compose logs -f agentgateway
```

### Operational notes (learned in production use)

- **The image is distroless** — no `/bin/sh`, `curl`, or `wget`, and no `health` subcommand. A
  shell/HTTP `healthcheck:` in Compose will not work; the gateway runs with **no healthcheck** and
  shows `running` (not `healthy`) in `docker compose ps`. A readiness endpoint is served on
  `:15021` if you need an external probe.
- **Mind the dependency direction.** If your agents/clients reach their **MCP tools through the
  gateway** and connect at startup, then the agents depend on the gateway — so the gateway must
  **not** `depends_on` those agents (that deadlocks). Gate the gateway only on its MCP backend(s);
  let A2A backends resolve lazily. A safe chain: `tool-server (healthy) → agentgateway (started) →
  agents (healthy) → orchestrator`.
- **The gateway caches backend connections.** If a backend container is recreated/restarted under a
  running gateway (new IP), the gateway returns `503 Connection refused` until it is restarted
  (`docker compose restart agentgateway`) or the stack is brought up cleanly. A clean
  `up` is unaffected (backends resolve at first request).
- **Verify the data path from the logs**, not just the outcome: the gateway logs
  `protocol=a2a a2a.method=message/send` and `protocol=mcp mcp.method.name=tools/call` per hop — the
  authoritative proof that traffic was actually proxied (an LLM can fake a tool-shaped answer).

---

## 6. Running the Binary

```bash
agentgateway -f config.yaml
```

Expected output:

```
info  state_manager  loaded config from File("config.yaml")
info  app            serving UI at http://localhost:15000/ui
info  proxy::gateway started bind bind="bind/3000"
```

---

## 7. Testing

### MCP — Inspector

```bash
npx @modelcontextprotocol/inspector http://localhost:3001/mcp   # match your MCP route's path
```

Or use the built-in playground at `http://localhost:15000/ui/playground`.

### A2A — curl

```bash
# Discover agent card (append the agent's path prefix when using path-based routing)
curl http://localhost:3000/agent/orchestrator/.well-known/agent-card.json

# Send a task (A2A method is message/send)
curl -X POST http://localhost:3000/agent/orchestrator \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Hello, agent!"}]
      }
    },
    "id": "1"
  }'
```

---

## 8. RBAC (Cedar Policies)

```yaml
binds:
  - port: 3000
    listeners:
      - routes:
          - policies:
              authorization:
                cedar:
                  policies:
                    - |
                      permit(
                        principal in Role::"analyst",
                        action == MCP::Action::"call_tool",
                        resource == MCP::Tool::"search_crm"
                      );
                    - |
                      forbid(
                        principal,
                        action == MCP::Action::"call_tool",
                        resource == MCP::Tool::"delete_record"
                      ) unless {
                        principal in Role::"admin"
                      };
```

---

## 9. LangGraph A2A Wiring

Wrap your compiled LangGraph graph in an A2A `AgentExecutor` using `a2a-sdk`:

```python
from fastapi import FastAPI
from a2a.server.apps import A2AStarlette
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.types import AgentCard, AgentSkill

app = FastAPI()

agent_card = AgentCard(
    name="My Orchestrator",
    description="LangGraph orchestrator agent",
    url="http://orchestrator-agent:9999/",
    version="1.0.0",
    skills=[AgentSkill(id="orchestrate", name="Orchestrate", description="Run the main workflow")]
)

executor = MyLangGraphAgentExecutor(graph=compiled_graph)
handler = DefaultRequestHandler(agent_executor=executor)
a2a_app = A2AStarlette(agent_card=agent_card, http_handler=handler)

app.mount("/", a2a_app)
```

Point `config.yaml` at this service: `backends: - host: orchestrator-agent:9999`.

---

## 10. Observability (OTel → GCP)

```yaml
config:
  telemetry:
    otel:
      endpoint: http://otel-collector:4317
      protocol: grpc
```

| Signal | GCP Destination |
|--------|----------------|
| Traces | Cloud Trace |
| Metrics | Cloud Monitoring |
| Logs | Cloud Logging (structured JSON) |

---

## Key Ports

| Port | Use |
|------|-----|
| `3000` | Primary A2A / MCP / HTTP traffic |
| `3001` | Optional second bind (e.g. MCP-only) |
| `15000` | Admin UI + Playground (localhost only by default) |

---

## Quick-Reference Config Patterns

| Goal | Pattern |
|------|---------|
| Single stdio MCP server | `mcp: targets: - name: X; stdio: ...` |
| Remote HTTP MCP server | `mcp: targets: - name: X; mcp: host: http://...` |
| Federate multiple MCP servers | Multiple entries under `mcp.targets` |
| Single A2A agent | `policies: { a2a: {} } → backends: - host: agent:port` |
| Multiple A2A agents | One route each: `matches: [{ path: { pathPrefix: /agent/x } }]` + `policies: { a2a: {}, urlRewrite: { path: { prefix: / } } }` |
| Combined A2A + MCP | Two `binds` entries on different ports |
| Docker Compose | Mount config; use service names; `ADMIN_ADDR=0.0.0.0:15000` |
| Kubernetes / GKE | See `references/REFERENCE.md` for Helm + CRD manifests |
| Tool-level RBAC | Cedar policy in `policies.authorization.cedar` |
| OTel export | `config.telemetry.otel.endpoint` |

For Kubernetes manifests, full config schema, and advanced patterns see [references/REFERENCE.md](references/REFERENCE.md).
