# Copyright 2023 Google LLC

"""Command line tool to version bump roles that are about to expire"""

from glob import glob
import subprocess
import click
import logging

from playground._playground_repository import PlaygroundRepository

logger = logging.getLogger(__name__)


def _git(cmd: list[str]) -> subprocess.CompletedProcess:
    cmd = ["git", "-c", "user.name=repository-playground", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"] + cmd
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    logger.debug("%s:\n%s", cmd, proc.stdout)
    return proc


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=False)
def bump_online(verbose: int, push: bool) -> None:
    """Commit new metadata versions for online roles if needed

    New versions will be signed.
    If --push, then current branch is also pushed to origin
    """
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    msg = f"Periodic online role version bump and resign\n\n"
    repo = PlaygroundRepository("metadata")
    snapshot_version = repo.bump_expiring("snapshot")
    if snapshot_version is not None:
        # if snapshot changes, we need to actually update timestamp content
        _, meta = repo.timestamp()
        assert meta
        timestamp_version = meta.version
        msg += f"snapshot v{snapshot_version}, timestamp v{timestamp_version}."
    else:
        timestamp_version = repo.bump_expiring("timestamp")
        if timestamp_version is not None:
            msg += f"timestamp v{timestamp_version}."

    if not timestamp_version and not snapshot_version:
        click.echo("No online version bumps needed")
        return

    click.echo(msg)
    _git(["commit", "-m", msg, "--", "metadata/timestamp.json", "metadata/snapshot.json"])
    if push:
        _git(["push", "origin", "HEAD"])

@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=False)
def bump_offline(verbose: int, push: bool) -> None:
    """Create new branches with version bump commits for expiring offline roles

    Note that these offline role versions will not be signed yet.
    If --push, the branches are pushed to origin. Otherwise local branches are
    created.
    """
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    repo = PlaygroundRepository("metadata")
    events=[]
    for filename in glob("*.json", root_dir="metadata"):
        if filename in ["timestamp.json", "snapshot.json"]:
            continue

        rolename = filename[:-len(".json")]
        version = repo.bump_expiring(rolename)
        if version is None:
            logging.debug("No version bump needed for %s", rolename)
            continue

        msg = f"Periodic version bump: {rolename} v{version}"
        event = f"sign/{rolename}-v{version}"
        _git(["commit", "-m", msg, "--", f"metadata/{rolename}.json"])
        try:
            _git(["show-ref", "--quiet", "--verify", f"refs/heads/{event}"])
            logging.debug("Signing event branch %s already exists", event)
        except subprocess.CalledProcessError:
            events.append(event)
            if push:
                _git(["push", "origin", f"HEAD:{event}"])
            else:
                _git(["branch", event])

        # get back to original HEAD (before we commited)
        _git(["reset", "--hard", "HEAD^"])

    # print out list of created event branches
    click.echo(" ".join(events))