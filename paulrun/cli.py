import click

from paulrun import settings


@click.group("paulrun")
@click.version_option(settings.VERSION)
def cli() -> None:
    """Run hand-written markdown runbooks."""
