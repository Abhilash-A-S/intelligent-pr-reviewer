# Authentication implementation validation

Implemented against the latest supplied `ZIP.zip`, archive SHA-256 `d0f540e540dc7c2f3556d70f8b86b745e96b5563af47f36450761efd8a6724d1`.

## Changes

- Added OIDC authorization-code sign-in with PKCE, state/browser binding, nonce and verified RS256 identity tokens.
- Added persistent server-side opaque login sessions, CSRF checks, expiry, sign-out, configuration errors and deny-by-default API authentication.
- Added explicit subject/group grants and per-repository Viewer, Reviewer, Publisher and Administrator permissions. Discovery/history responses are filtered; unknown/forbidden job IDs do not disclose results.
- Added job owner identity and owner/admin cancellation checks. Worker start and delegated provider calls recheck policy; job authorization is bounded by the original session deadline.
- Added a responsive theme-aware sign-in page, guards/interceptor, signed-in user display and permission-aware controls. The existing shared theme stylesheet is byte-for-byte unchanged.
- Added placeholder configuration, an example policy and `AUTHENTICATION_SETUP.md`. No production credentials or user policy/session databases are shipped.

## Completed checks

- **1,324 backend tests passed**, including 54 security/authentication additions. Test dependencies follow the updated lock file; outbound network connections were disabled for the final backend run.
- **47 frontend tests passed**, including session restore/expiry/logout, CSRF interception, role/repository scoping and cancellation checks.
- Production frontend build passed and verified 31 embedded assets. Initial bundle is about 665 kB against the existing 600 kB warning / 1 MB error thresholds; budgets were not changed.
- Python source distribution and wheel builds passed; the wheel was checked for the new security module and all embedded UI assets.
- Browser checks passed for sign-in in both themes at widths 1920, 1440, 1024, 836, 760, 390 and 320px; protected pages were exercised in both themes at 1440, 836, 390 and 320px. Checked missing configuration, role-aware actions, reload/session restore, sign-out, expired-session redirect and CSRF headers. No browser JavaScript errors were seen. Browser identity/provider responses were controlled test fixtures.

## Limits and pre-existing issue

Live Entra/company sign-in could not be exercised without an organization app registration and credentials. Complete the live acceptance steps in the setup guide. No real provider comments were posted.

The uploaded Review in Progress page already overflows horizontally at mobile widths with long activity filenames (baseline: 390px viewport / 414px document). This was reproduced using the unmodified uploaded UI, left unchanged and recorded as an existing design issue. Other checked routes and the new sign-in page fit the tested viewports. Browser screenshots were used only for internal inspection and are not included as deliverables.

This release implements authentication/authorization, not all audit remediation. Review jobs/history are still in memory; durable review storage, restart recovery, admission/retention limits and generalized error sanitization remain planned work. The SQLite database added here persists authentication sessions, not review jobs.
