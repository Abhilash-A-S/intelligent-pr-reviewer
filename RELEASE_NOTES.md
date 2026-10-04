# Reference-Aligned UI Release

This release adds the first complete web experience without replacing or
forking the existing universal review engine.

## Delivered

- Angular 20 standalone application with a custom responsive design system
- Dashboard, pull-request details, progress, results, history, and settings
- Layout, density, typography, colors, controls, cards, tables, and status
  treatments aligned to the six approved light/dark product mockups
- Horizontal review pipeline, compact runtime metrics, activity feed, and live
  diagnostics matching the approved progress view
- Filterable audit table followed by the review-quality trend visualization
- Two-column settings workspace with provider, model, defaults, publishing, and
  performance panels visible in one cohesive view
- Light/dark theme persistence and Lucide iconography
- GitHub and Azure DevOps repository selection
- FastAPI endpoints for provider health, PR discovery, changed files, review
  creation, progress polling, results, history summaries, and queued-job cancel
- Explicit publish confirmation and server-only credential handling
- Review depth and worker preferences connected to real review requests
- Embedded optimized Angular assets for single-process deployment
- CLI behavior and the provider-neutral orchestration pipeline preserved

## Verification

- Python: `1258 passed`
- Angular: `5 SUCCESS`
- Production npm audit: `0 vulnerabilities`
- Angular production bundle: 575.58 kB raw / 109.28 kB estimated transfer
- Six reference-width desktop routes (836 px) and all six 390 px mobile routes
  browser-audited with no runtime errors or page-level horizontal overflow
- Publish confirmation and persisted light/dark theme interactions verified

## Intentional first-release boundaries

- Review-job history is held for the current API process; persistent database
  storage and multi-user authentication are separate product increments.
- Repository framework/project context is resolved by the review engine during
  execution; the PR details page does not guess it before discovery.
- Test, CI/CD, ownership, validation, deduplication, and publishing safeguards
  remain policy-controlled so browser settings cannot weaken review safety.
