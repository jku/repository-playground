# Copyright 2023 Google LLC

"""Command line tool to compile a publishable TUF repository for Repository Playground CI"""

import click
import logging
import os

from playground._playground_repository import PlaygroundRepository


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.argument("publish-dir")
def publish(verbose: int, publish_dir: str) -> None:
    """Create a metadata directory that is ready to publish
    
    In practice, creates versioned files for all metadata that is part of
    the repository"""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    os.makedirs(publish_dir, exist_ok=True)
    PlaygroundRepository("metadata").publish(publish_dir)
