# PROVENANCE: original | domain plugin registry per DOMAIN_BUILD_TEMPLATE.md
"""Domain plugin registry — auto-discovers domain subpackages.

Each subpackage under ``kairo.domains`` defines a ``DOMAIN`` descriptor
and calls ``register(DOMAIN)`` at import time.  ``discover()`` imports
every subpackage via ``pkgutil.iter_modules`` and returns the accumulated
list.

A new domain needs ONLY:
  1. ``kairo/domains/<name>/__init__.py``  — defines DOMAIN, calls register()
  2. ``kairo/domains/<name>/requirements.txt``  — per-domain deps (optional)

No shared files (cli.py, STATUS.md, requirements-test.txt) need editing.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Domain:
    """Descriptor for a registered domain.

    Attributes:
        name:        Internal domain name (e.g. ``"legal_redline"``).
        cli_name:    CLI subcommand name (e.g. ``"redline"``).
        status:      ``"Real"``, ``"Experimental"``, or ``"prompt-only"``.
        summary:     One-line summary for STATUS.md generation.
        register_cli: Callback that adds this domain's subparser(s) to the
                      argparse subparsers action.
        run:         Callback that executes the domain's CLI command.
        requirements: List of pip requirement strings for this domain.
    """

    name: str
    cli_name: str
    status: str
    summary: str
    register_cli: Callable[[argparse._SubParsersAction], None]
    run: Callable[[argparse.Namespace], int]
    requirements: list[str] = field(default_factory=list)


# Module-level registry
_registry: list[Domain] = []


def register(domain: Domain) -> None:
    """Register a domain descriptor. Called by each domain's __init__.py."""
    _registry.append(domain)


def discover() -> list[Domain]:
    """Auto-discover and import all domain subpackages, returning the registry.

    Imports every subpackage under ``kairo.domains`` via ``pkgutil.iter_modules``,
    which triggers each subpackage's ``__init__.py`` and its ``register()`` call.
    """
    import kairo.domains as pkg

    for _importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
        if ispkg:
            importlib.import_module(f"kairo.domains.{modname}")
    return list(_registry)


def get_domains() -> list[Domain]:
    """Return the current registry without triggering discovery."""
    return list(_registry)
