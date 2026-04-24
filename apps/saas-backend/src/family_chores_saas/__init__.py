"""SaaS deployment scaffold for Family Chores — Phase 3 placeholder.

Public surface: `create_app()` returns a FastAPI app where every
tenant-scoped endpoint returns 501 (`PlaceholderAuthStrategy`) but
`/api/health` returns 200. Step 10 of the Phase 2 refactor wires this
together so the workspace can grow real SaaS code in Phase 3 without
re-litigating the composition pattern.

See `DECISIONS.md` §11.
"""

__version__ = "0.1.0"


def create_app():  # type: ignore[no-untyped-def]
    """Lazy import wrapper — keeps `import family_chores_saas` cheap."""
    from family_chores_saas.app_factory import create_app as _create

    return _create()


__all__ = ["__version__", "create_app"]
