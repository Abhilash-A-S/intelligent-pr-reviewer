# Live Review Diagnostics and Dashboard Stabilization Release

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
- GitHub account/organization and repository discovery from live provider APIs
- Azure DevOps organization, project, and repository discovery from live APIs
- Searchable, keyboard-accessible custom selects with checked selection,
  loading, empty, error, Escape/outside-click closing, and manual entry fallback
- Custom selects used consistently for dashboard, history, and finding filters;
  no browser-native product dropdowns remain
- Larger product header with integration health beside the theme control and a
  compact mobile health popover
- Purple active-provider treatment plus subtle indigo, amber, red, and green
  dashboard metric depth in both themes
- Truthful provider health states that distinguish configured, validated,
  authentication-failed, unavailable, and not-configured connections
- Lightweight, bounded changed-file count enrichment for open pull requests
- Restored rounded branch/status/count treatments and visible row hover states
- Compact filtered-empty state with an immediate clear-filters action
- Provider switching resets stale pull-request search and status filters
- Empty discovery queries are omitted and restricted discovery has a clear,
  provider-neutral manual-entry fallback
- Structured live review metrics for changed files, review files, static
  findings, and actual/planned LLM calls before the review completes
- Structured diagnostic events with timestamps, phases, batch/file context,
  token estimates, validation, quality-gate, and publishing milestones
- Separate current-activity and filterable live-diagnostics panels with bounded
  internal scrolling and matching responsive light/dark behavior
- Correct sidebar ownership highlighting across PR detail, progress, results,
  history, and settings routes
- Compact sticky inner-page headings beneath the persistent application header
- Figma-matched compact dashboard metrics with status tints, circular icons,
  dynamic counts, and equivalent light/dark treatments
- Correct document scroll ownership so the pull-request identity header remains
  fully visible below the fixed application header instead of being clipped
- Restored the intended single-column PR/results/progress layout on narrow
  screens after a later desktop grid override had taken precedence
- FastAPI endpoints for provider health, PR discovery, changed files, review
  creation, progress polling, results, history summaries, and queued-job cancel
- Explicit publish confirmation and server-only credential handling
- Review depth and worker preferences connected to real review requests
- Embedded optimized Angular assets for single-process deployment
- Embedded-asset cleanup and verification so old hashed bundles cannot ship
- CLI behavior and the provider-neutral orchestration pipeline preserved

## Verification

- Python: `1267 passed`
- Angular: `20 SUCCESS`
- Production npm audit: `0 vulnerabilities`
- Angular production bundle: 591.66 kB raw / 110.42 kB estimated transfer
- Embedded UI: 18 reachable assets; no stale preview bundle included
- Provider discovery API contracts verified against GitHub and Azure adapter
  tests, including Azure configured-organization fallback
- Dashboard data rows, changed-file counts, hover states, status pills, progress
  metrics, activity, diagnostics, and integration health browser-audited
- Dashboard metrics and sticky PR context browser-audited in light, dark,
  desktop, and 390 px mobile views with no page-level horizontal overflow
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
