# PROVENANCE: original | domain plugin registry package
"""kairo.domains — plugin registry for Kairo Phantom domains.

Each subpackage under ``kairo.domains`` defines a ``DOMAIN`` descriptor
and registers it via ``kairo.domains.registry.register()``.

Use ``kairo.domains.registry.discover()`` to auto-discover all registered
domains.
"""
