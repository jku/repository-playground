# Copyright 2023 Google LLC

"""Command line tool to update timestamp for Repository Playground CI"""

import click
import logging

from playground._playground_repository import PlaygroundRepository

logger = logging.getLogger(__name__)

@click.command()
@click.option("-v", "--verbose", count=True, default=0)
def timestamp(verbose: int) -> None:
    """Update The TUF timestamp based on current repository content"""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    repo = PlaygroundRepository("metadata")
    repo.timestamp()
