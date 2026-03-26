from __future__ import annotations

import os

from ragin.runtime.base import BaseRuntimeProvider


def get_default_provider() -> BaseRuntimeProvider:
    """
    Resolves the runtime provider from settings.PROVIDER.
    Defaults to LocalProvider when not configured (dev / test).

    Valid values: aws | gcp | azure | local
    """
    from ragin.conf import settings
    name = settings.PROVIDER.lower()

    if name == "aws":
        from ragin.runtime.aws import AWSProvider
        return AWSProvider()
    if name == "gcp":
        from ragin.runtime.gcp import GCPProvider
        return GCPProvider()
    if name == "azure":
        from ragin.runtime.azure import AzureProvider
        return AzureProvider()
    if name == "local":
        from ragin.runtime.local import LocalProvider
        return LocalProvider()

    raise ValueError(
        f"Unknown RAGIN_PROVIDER={name!r}. Valid values: aws, gcp, azure, local"
    )


__all__ = [
    "BaseRuntimeProvider",
    "get_default_provider",
]
