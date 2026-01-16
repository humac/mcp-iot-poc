# Auth0 Integration Plan (Future)

## Overview
Replace basic auth with Auth0 OIDC for dashboard login and optionally M2M tokens for MCP server authorization.

## Prerequisites

### Auth0 Console Setup

**1. Create Regular Web Application:**
- Auth0 Dashboard → Applications → Create Application
- Type: "Regular Web Application"
- Settings:
  - Allowed Callback URLs: `http://localhost:8080/callback`
  - Allowed Logout URLs: `http://localhost:8080`

**2. Create API (for M2M):**
- Auth0 Dashboard → APIs → Create API
- Identifier: `https://mcp-iot-api`
- Permissions: `read:thermostat`, `write:thermostat`, `admin`

**3. Create M2M Application:**
- Auth0 Dashboard → Applications → Create Application
- Type: "Machine to Machine"
- Authorize for the API created above

## Environment Variables

```bash
# Dashboard Auth (OIDC)
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_CLIENT_ID=xxxxxxxxxxxx
AUTH0_CLIENT_SECRET=xxxxxxxxxxxx
AUTH0_CALLBACK_URL=http://localhost:8080/callback

# MCP Auth (M2M) - Optional
AUTH0_API_AUDIENCE=https://mcp-iot-api
AUTH0_M2M_CLIENT_ID=yyyyyyyyyyyy
AUTH0_M2M_CLIENT_SECRET=yyyyyyyyyyyy
```

## Implementation Steps

### Phase 1: Dashboard Login
- [ ] Add `authlib` dependency to agent
- [ ] Create `/login`, `/callback`, `/logout` routes
- [ ] Store session in secure cookie (or Redis)
- [ ] Protect all `/api/*` routes with session check
- [ ] Update dashboard UI with login/logout buttons + user info

### Phase 2: JWT Validation on API
- [ ] Validate Auth0 JWTs on API endpoints
- [ ] Extract user info from token (email, roles)
- [ ] Implement role-based access (admin vs viewer)

### Phase 3: M2M for MCP Servers
- [ ] Agent fetches M2M token from Auth0 on startup
- [ ] MCP servers validate JWTs (not shared secrets)
- [ ] Token refresh logic before expiry

## Files to Modify

| File | Changes |
|------|---------|
| `agent/pyproject.toml` | Add `authlib`, `python-jose` deps |
| `web_dashboard.py` | Add login/callback/logout routes, session middleware |
| `mcp_client.py` | Fetch M2M token, send JWT instead of static token |
| `servers/*/server.py` | Validate JWT instead of bearer token |
| `docker-compose.yml` | Add Auth0 env vars |
