# Intelligent PR Reviewer

Intelligent PR Reviewer is a provider-neutral pull-request review platform for
GitHub and Azure DevOps. It combines deterministic analysis with bounded,
evidence-grounded LLM review, framework-aware validation, root-cause
deduplication, and duplicate-safe publishing.

This release adds a production-style Angular workspace on top of the existing
Python engine. The CLI remains fully supported and the FastAPI layer calls the
same `ReviewOrchestrator`; review logic is not duplicated in the UI.

## Included web experience

- Provider and repository selection with an open-PR dashboard
- Pull-request details, changed files, dry-run and publish actions
- Explicit confirmation before any provider write
- Live background-job progress and safe status polling
- Professional finding results, filtering, quality gate and JSON export
- Current-session review history
- GitHub, Azure DevOps and Ollama connection health
- Light and dark themes, responsive navigation and Lucide icons
- Server-only provider credentials; tokens never enter the browser bundle

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- Node.js supported by Angular 20 (Node 20.19+, 22.12+ or 24+)
- Ollama when semantic review is enabled

## First-time setup

```powershell
uv sync
Copy-Item .env.example .env
cd web
npm ci
cd ..
```

Add the required provider token to `.env`. Keep `.env` local and never commit
it. GitHub uses `owner/repository`; Azure DevOps uses
`organization/project/repository`.

## Run the complete application

Build the optimized Angular client into the Python package, then start FastAPI:

```powershell
cd web
npm run build:embedded
cd ..
uv run intelligent-pr-reviewer-api
```

Open `http://127.0.0.1:8000`. FastAPI serves the Angular application and all
`/api` routes from one process.

## Frontend development with live reload

Run these in two terminals:

```powershell
# Terminal 1
uv run intelligent-pr-reviewer-api

# Terminal 2
cd web
npm start
```

Open `http://localhost:4200`. Angular proxies `/api` to port 8000.

## Verification

```powershell
uv run pytest -q

cd web
npm run build
npm run test:ci
```

`npm run test:ci` requires Chrome or Chromium. The optimized initial bundle is
kept below the configured 600 kB warning budget and feature pages are lazy
loaded.

## CLI remains available

```powershell
uv run intelligent-pr-reviewer `
  --provider github `
  --repository owner/repository `
  --pull-number 1 `
  --dry-run
```

Use `--publish` only after checking the dry-run findings. Re-running publish is
safe: finding markers prevent duplicate inline comments and the summary is
updated instead of duplicated.
