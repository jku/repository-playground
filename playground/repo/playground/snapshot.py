# Copyright 2023 Google LLC

"""Command line tool to compile a publishable TUF repository for Repository Playground CI"""

import click
import logging
import os

from playground._playground_repository import PlaygroundRepository

logger = logging.getLogger(__name__)

@click.command()
@click.option("-v", "--verbose", count=True, default=0)
def snapshot(verbose: int) -> None:
    """Update The TUF snapshot based on current repository content"""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    repo = PlaygroundRepository("metadata")
    snapshot_updated, _ = repo.snapshot()
    if snapshot_updated:
        repo.timestamp()
