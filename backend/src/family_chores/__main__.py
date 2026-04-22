"""Uvicorn entrypoint — invoked as `python -m family_chores`."""

from __future__ import annotations

import uvicorn

from family_chores.config import load_options


def main() -> None:
    options = load_options()
    uvicorn.run(
        "family_chores.app:create_app",
        host="0.0.0.0",
        port=8099,
        factory=True,
        log_level=options.log_level.lower(),
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=options.log_level.lower() == "debug",
    )


if __name__ == "__main__":
    main()
