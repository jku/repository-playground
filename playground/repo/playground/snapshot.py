# Copyright 2023 Google LLC

"""Command line tool to update snapshot (and timestamp) for Repository Playground CI"""

import subprocess
import sys
from tempfile import mkdtemp
import click
import logging

from playground._playground_repository import PlaygroundRepository

logger = logging.getLogger(__name__)


def _git(cmd: list[str]) -> subprocess.CompletedProcess:
    cmd = ["git", "-c", "user.name=repository-playground", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"] + cmd
    proc = subprocess.run(cmd, check=True, text=True)
    logger.debug("%s:\n%s", cmd, proc.stdout)
    return proc


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=False)
@click.argument("publish-dir", required=False)
def snapshot(verbose: int, push: bool, publish_dir: str|None) -> None:
    """Update The TUF snapshot based on current repository content

    Create a commit with the snapshot and timestamp changes (if any).
    If --push, the commit is pushed to origin.
    If publish-dir is provided, a repository snapshot is generated into that directory

    returns 1 if no snapshot was generated
    """
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    repo = PlaygroundRepository("metadata")
    snapshot_updated, _ = repo.snapshot()
    if not snapshot_updated:
        click.echo("No snapshot needed")
        sys.exit(1)

    repo.timestamp()

    msg = "Snapshot & timestamp"
    _git(["add", "metadata/timestamp.json", "metadata/snapshot.json"])
    _git(["commit", "-m", msg])
    if push:
        _git(["push", "origin", "HEAD"])

    if publish_dir:
        repo.publish(publish_dir)
        click.echo(f"New repository snapshot generated and published in {publish_dir}")
    else:
        click.echo(f"New repository snapshot generated")
