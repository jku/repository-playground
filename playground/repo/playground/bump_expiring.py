# Copyright 2023 Google LLC

"""Command line tool to version bump roles that are about to expire"""

import click
import logging

from playground._playground_repository import PlaygroundRepository

logger = logging.getLogger(__name__)

@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.argument("rolename")
def bump_expiring(verbose: int, rolename: str) -> None:
    """"""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    repo = PlaygroundRepository("metadata")
    version = repo.bump_expiring(rolename)
    if version is None:
        click.echo(f"{rolename} is not about to expire: no version bump needed")
    else:
        click.echo(f"{rolename} bumped to v{version}")
