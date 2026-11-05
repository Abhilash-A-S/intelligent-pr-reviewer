import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "pr_reviewer.web.api:app",
        host=os.getenv("PR_REVIEW_API_HOST", "127.0.0.1"),
        port=int(os.getenv("PR_REVIEW_API_PORT", "8000")),
        reload=False,
        access_log=False,  # OIDC callback query strings contain single-use authorization codes.
    )


if __name__ == "__main__":
    main()
