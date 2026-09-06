
## Universal review-engine architecture

The reviewer core is technology-agnostic. A central rule registry owns canonical
rule IDs, aliases, severity boundaries, finding provenance, and whether an AI
reviewer may create a rule independently.

Key boundaries:

- deterministic/framework/compiler-owned rule families are authoritative;
- LLM findings carry explicit provenance and cannot independently recreate
  deterministic rule families;
- unknown LLM rule IDs are rejected rather than silently expanding product
  behavior;
- AI-created findings use registered universal semantic categories such as
  correctness, reliability, API misuse, data validation, concurrency,
  security, performance, and maintainability;
- language/framework/build/workspace support is implemented as evidence and
  capability adapters while the core finding pipeline remains unchanged.

See `ARCHITECTURE_PLAN_UNIVERSAL_REVIEW_ENGINE.md` for the staged design.

## Local large-PR performance

Ollama supports ownership-safe batching for compatible files. Batches may
cross Nx project roots only when the resolved framework and review strategy
match. Every prompt carries the individual file's project/framework context,
and every returned finding remains restricted to an exact changed file and
line. Large but bounded source files use one call instead of arbitrary
line-count splitting.

Start with one active local inference:

```env
OLLAMA_MAX_CONCURRENT_REVIEWS=1
OLLAMA_MAX_ATTEMPTS=1
OLLAMA_NUM_PREDICT=1024
```

Each run reports review batches, planned/actual LLM calls, retries, ownership,
skip categories, phase timings, and total review time.

### Review depth

`standard` is the recommended default. It preserves business logic, API,
security, test, template, configuration, and framework-semantic review while
excluding only explainable low-value or deterministically saturated changes.

```bash
uv run intelligent-pr-reviewer --repository owner/repo --pull-number 1 --review-depth standard --dry-run
```

- `fast`: requires a high-value semantic signal and minimizes local inference.
- `standard`: balanced professional review; used when the option is omitted.
- `deep`: sends every normally eligible file to semantic review.

Ollama diagnostics report every call's files, prompt/output tokens, prompt
evaluation time, generation time, raw findings, and aggregate surviving AI
findings.
