"""Service layer — domain logic that needs an async session.

`core/` is pure Python (no I/O). `services/` is the thin async layer that
queries SQLAlchemy, calls into `core/`, and writes results back.
"""
