from __future__ import annotations

import importlib
import sys

import click


@click.group()
def main() -> None:
    """ragin — Model-First Serverless Framework."""


@main.command()
@click.argument("name")
@click.option("--dir", "directory", default=None,
              help="Target directory (defaults to ./<name>).")
def start(name: str, directory: str | None) -> None:
    """Scaffold a new ragin project with main.py + settings.py."""
    from ragin.cli.scaffold import scaffold_project

    try:
        path = scaffold_project(name, directory)
    except FileExistsError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"Created ragin project '{name}' at {path}/")
    click.echo("")
    click.echo("  Next steps:")
    click.echo(f"    cd {name}")
    click.echo("    # edit settings.py  (database, provider, …)")
    click.echo("    # edit main.py      (define your models)")
    click.echo("    ragin dev")


@main.command()
@click.option("--app", "app_path", default=None,
              help="Module and app variable, e.g. main:app")
@click.option("--host", default=None, type=str)
@click.option("--port", default=None, type=int)
def dev(app_path: str | None, host: str | None, port: int | None) -> None:
    """Start the local development server."""
    from ragin.conf import settings

    app_path = app_path or settings.APP
    host = host or settings.HOST
    port = port or settings.PORT

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
