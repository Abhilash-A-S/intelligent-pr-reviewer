# Team sign-in and authorization

This release adds the four requested controls to the latest supplied project:

1. OIDC sign-in and a server-side identity check on protected requests.
2. Explicit repository permissions for discovery, PR reads, reviews and results.
3. Job owner identity, repository-scoped history/results and owner/admin cancellation.
4. A distinct publishing permission enforced on the server, not just by the UI.

## Configure Microsoft Entra ID

Use a **single-tenant confidential Web application**, not a browser-only SPA registration. The backend owns the authorization-code exchange. No identity-provider access/ID tokens are stored in Angular, browser local storage or the session database.

1. Register the Web app with your organization administrator. Obtain the Directory (tenant) ID, Application (client) ID and a client-secret **value**. Put these in your local `.env` or deployment secret manager; do not commit them.
2. Register this exact Web redirect URI: `https://YOUR-APP-HOST/api/auth/callback`. For local development, use `http://127.0.0.1:8000/api/auth/callback` and `PR_REVIEW_PUBLIC_URL=http://127.0.0.1:8000`. Register the local URI explicitly too. Do not configure a wildcard redirect.
3. Configure `.env` from `.env.example`. Set `PR_REVIEW_ENTRA_TENANT_ID`, `PR_REVIEW_OIDC_CLIENT_ID`, `PR_REVIEW_OIDC_CLIENT_SECRET`, `PR_REVIEW_PUBLIC_URL`, `PR_REVIEW_ACCESS_POLICY`, and `PR_REVIEW_AUTH_DB`.
4. Copy `access-policy.example.json` to the local path `access-policy.json`. Replace the example repository names with real canonical identifiers. Start with `{"grants":[]}` if you need to discover your own subject first: sign in successfully, then the app's “No repositories assigned” panel displays your account ID. Assign that exact ID to a policy grant and reload. There is no first-user-auto-admin behavior.
5. For group grants, configure Entra group claims in **ID tokens** and use group object IDs, not display names. Group overage is not resolved through Graph: if group IDs are omitted from the token, group-only grants deny access. Use an explicit subject grant or configure appropriately scoped group claims. Only `openid profile` scopes are requested; no Graph access is requested.
6. Build and start:

```powershell
uv sync
cd web
npm ci
npm run build:embedded
cd ..
uv run intelligent-pr-reviewer-api
```

Missing configuration blocks protected web APIs with 503 and presents an explanatory login page. An unauthenticated request with configured sign-in receives 401. No demo credentials, identity headers, password endpoint or auth-disable switch exist.

The OIDC issuer may instead be supplied through `PR_REVIEW_OIDC_ISSUER` for another provider implementing confidential authorization-code OIDC with PKCE S256 and RS256 ID tokens. Discovery must return the exact issuer; endpoints must be HTTPS. Live compatibility with a non-Entra provider is not certified by the mocked tests.

## Permissions

Grants use `subjects` and/or `groups` as OR selectors, an exact lowercase role, and explicit repository lists keyed by `github` or `azure-devops`. Subject IDs are the exact `issuer|sub` shown by `/api/auth/me`. Email addresses and arbitrary browser identity headers are not accepted as identity. No wildcard repositories are supported.

| Role | Read permitted repositories/jobs | Start dry review | Publish | Cancel |
| --- | --- | --- | --- | --- |
| viewer | Yes | No | No | No |
| reviewer | Yes | Yes | No | Own queued jobs |
| publisher | Yes | Yes | Yes | Own queued jobs |
| administrator | Yes | Yes | Yes | Any queued job within assigned repositories |

Multiple matching grants combine using the highest role **per repository**. Administrator is not a global wildcard. These administrators have job-control privileges; changing the access-policy file remains a server-administrator operation. A web-based user/role management console is not included.

Organization/project/repository discovery is filtered before response counts are calculated. Disallowed scopes are rejected before provider discovery calls. Job results are deliberately shared with authorized members of the same repository; they are not restricted exclusively to their creator. Jobs from other repositories return 404, and history omits them. Legacy jobs without a recognized repository or owner never receive an implicit owner/admin identity.

Policy is read from the server file on each check. Invalid/missing policy denies access. Changes to explicit grants take effect without restarting. Group membership is captured from the signed ID token at login, so group-membership changes require reauthentication or session expiry. The policy is checked at submission, worker start and before delegated provider operations, including publishing. The job authorization also expires at the original session deadline. Queued/long-running jobs reaching that deadline stop before subsequent provider operations; sign in and request a new review. An already in-flight upstream request cannot be recalled; a batch already sent may have partial writes.

## Sessions and browser behavior

- Opaque random session cookies are HttpOnly, SameSite=Lax and Secure on HTTPS. Production uses a host-only `__Host-` session cookie. HTTP is permitted only for loopback development.
- Session records and one-use login transactions live in SQLite; only hashed cookie identifiers are stored. ID tokens, access tokens and client secrets are not persisted there. Protect/back up this server directory; filesystem access is sensitive.
- Login uses state, a separate browser-binding cookie, nonce, PKCE S256 and one-use transaction consumption. JWT signatures, RS256 algorithm, issuer, audience, nonce, expiry and required claims are verified.
- Session lifetime is capped by the ID-token expiry and eight hours, whichever is earlier. There is no silent refresh yet. Reload restores a valid session; expiry redirects to sign-in.
- State-changing requests require a session-specific `X-CSRF-Token`; a supplied Origin must exactly match the public app origin. Angular obtains the CSRF value from `/api/auth/me` and keeps it in memory. External requests do not receive it.
- Logout revokes the application session on the server and removes the cookie. This does not terminate the organization's global SSO session; signing in again may reuse company SSO.
- The supplied CLI entry point disables raw access logs because authorization codes arrive on the callback query string. If you launch Uvicorn another way, use `--no-access-log` or redact authentication query strings. Apply the same rule at reverse proxies and request-tracing systems. Never log cookies, tokens, client secrets, codes or CSRF values.
- Backend review-request audit events include the actor, canonical repository, job ID and publish flag. Configure secure log collection/retention separately; this is not a complete persistent audit-trail service.
- Same-origin deployment is supported. For Angular development, set `PR_REVIEW_PUBLIC_URL=http://localhost:4200`, register that callback URI, access the UI on that exact origin and retain the `/api` dev proxy. Do not mix localhost and 127.0.0.1 origins.

## Tests and limitations

Run `uv run pytest -q` and `cd web; npm run test:ci` (Chrome/Chromium required). Existing API regression fixtures now explicitly establish a test session; anonymous-denial tests are separate. Test-only session creation lives in tests, not exposed application endpoints.

Tests cover unauthorized/expired/forged sessions, denial before queue/provider calls, role separation, repository visibility, cross-job access/cancellation, CSRF/origin failures, policy changes, signed-token verification failures, nonce/browser binding and callback replay, logout/revocation and auth-service recreation. Browser checks cover the sign-in layout and permission/session UX using controlled API fixtures.

**Required live acceptance:** your organization must register/configure Entra ID, assign users/groups and run real login, logout, expiry and representative role checks. No tenant credentials were supplied, so live company sign-in cannot be certified here. No real GitHub/Azure comments were posted during automated checks.

This is the authentication stage, not a declaration of full production readiness. Review jobs/history are still in-memory; their durability and restart recovery are the next planned stage. Queue/retention caps, generalized error sanitization and other findings from the earlier audit remain separate work. HTTP provider credentials remain server-side service-account credentials; application grants limit who can invoke them. The CLI remains a trusted server-operator interface, outside browser-user sign-in policy.

## Protocol references

- Microsoft authorization-code flow: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow
- Microsoft OIDC: https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc
- PyJWT verification API: https://pyjwt.readthedocs.io/en/latest/api.html
