# Live-Data UI Release

This release connects the complete web experience to live provider and review
engine APIs without replacing or forking the existing universal review engine.

## Delivered

- Angular 20 standalone application with a custom responsive design system
- All seeded/demo pull requests, findings, jobs, history, dates, metrics, and
  configuration fallbacks removed from product code and embedded assets
- Dashboard, pull-request details, progress, results, history, and settings
- Live GitHub/Azure pull-request timestamps, descriptions, commit counts, and
  changed-file statistics
- Review status derived from actual current-session jobs
- Live history metrics and 31-day quality trend calculated from API jobs
- Runtime Ollama and publishing-policy settings reported by FastAPI
- Purpose-built loading, empty, unavailable, filtered-empty, and provider-error
  states; an empty API response never falls back to sample content
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
- Embedded-asset cleanup and verification so old hashed bundles cannot ship
- CLI behavior and the provider-neutral orchestration pipeline preserved

## Verification

- Python: `1260 passed`
- Angular: `9 SUCCESS`
- Production npm audit: `0 vulnerabilities`
- Angular production bundle: 576.43 kB raw / 109.52 kB estimated transfer
- Embedded UI: 16 reachable assets; no stale preview bundle included
- Six reference-width desktop routes (836 px) and all six 390 px mobile routes
  browser-audited with no runtime errors or page-level horizontal overflow
- Missing PR/job routes, publish confirmation, and persisted light/dark theme
  interactions verified

## Intentional first-release boundaries

- Review-job history is held for the current API process; persistent database
  storage and multi-user authentication are separate product increments.
- Repository framework/project context is resolved by the review engine during
  execution; the PR details page does not guess it before discovery.
- Test, CI/CD, ownership, validation, deduplication, and publishing safeguards
  remain policy-controlled so browser settings cannot weaken review safety.
