from __future__ import annotations

import importlib
import sys

import click


@click.group()
def main() -> None:
    """ragin — Model-First Serverless Framework."""


@main.command()
@click.option("--app", "app_path", default="main:app", show_default=True,
              help="Module and app variable, e.g. main:app")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
def dev(app_path: str, host: str, port: int) -> None:
    """Start the local development server."""
    app_obj = _load_app(app_path)
    from ragin.cli.dev_server import run_dev_server
    run_dev_server(app_obj, host=host, port=port)


@main.command()
@click.option("--app", "app_path", default="main:app", show_default=True)
@click.option("--provider", default="aws", show_default=True,
              type=click.Choice(["aws", "gcp", "azure"]),
              help="Target cloud provider.")
@click.option("--output", default="build", show_default=True,
              help="Output directory.")
@click.option("--module", default="main", show_default=True,
              help="Python module name of the user app (used in generated entry).")
def build(app_path: str, provider: str, output: str, module: str) -> None:
    """Generate routes.json and the provider entry point."""
    _load_app(app_path)  # import so @resource decorators run and routes are registered
    from ragin.cli.builder import build_app
    from ragin.core.registry import registry
    build_app(None, output_dir=output, provider=provider, module=module)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _load_app(app_path: str):
    """Import module and return the app variable from 'module:attr' syntax."""
    if ":" not in app_path:
        raise click.BadParameter(f"app must be 'module:attr', got {app_path!r}")
    module_name, attr = app_path.split(":", 1)
    sys.path.insert(0, ".")
    mod = importlib.import_module(module_name)
    app_obj = getattr(mod, attr, None)
    if app_obj is None:
        raise click.BadParameter(f"No attribute {attr!r} in module {module_name!r}")
    return app_obj
