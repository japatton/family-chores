"""Bundled data files for family_chores_core.

The presence of this `__init__.py` makes `data` a real subpackage so that
`importlib.resources.files("family_chores_core.data")` resolves cleanly
across editable installs, wheels, and the addon's Docker layer. Any
non-Python files under here are shipped via the `[tool.setuptools.package-data]`
declaration in `packages/core/pyproject.toml`.
"""
