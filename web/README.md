# Intelligent PR Reviewer UI

Angular 20 standalone frontend for the Intelligent PR Reviewer FastAPI service.
It uses a custom responsive design system, lazy-loaded screens, signals, the
Angular HTTP client and Lucide icons.

## Commands

```powershell
npm ci
npm start              # Live development at http://localhost:4200
npm run build          # Normal optimized build under web/dist
npm run build:embedded # Optimized build embedded in the Python package
npm run test:ci        # Headless unit tests
```

During development, `/api` is proxied to `http://127.0.0.1:8000`. Start the API
from the repository root with `uv run intelligent-pr-reviewer-api`.

The browser stores only non-sensitive workspace and review preferences.
Provider tokens, PATs and Ollama connectivity stay behind FastAPI.
