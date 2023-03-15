# Copyright 2023 Google LLC

"""Command line signing event status output tool for Repository Playground CI"""

import filecmp
from glob import glob
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
import click
import logging

from playground._playground_repository import PlaygroundRepository

logger = logging.getLogger(__name__)

def _git(cmd: list[str]) -> subprocess.CompletedProcess:
    cmd = ["git", "-c", "user.name=repository-playground", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"] + cmd
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    logger.debug("%s:\n%s", cmd, proc.stdout)
    return proc


def _find_changed_roles(known_good_dir: str, signing_event_dir: str) -> list[str]:
    # find the files that have changed or been added
    # TODO what about removed?

    files = glob("*.json", root_dir=signing_event_dir)
    changed_roles = []
    for fname in files:
        if (
            not os.path.exists(f"{known_good_dir}/{fname}") or
            not filecmp.cmp(f"{signing_event_dir}/{fname}", f"{known_good_dir}/{fname}",  shallow=False)
        ):
            if fname in ["timestamp.json", "snapshot.json"]:
                assert("Unexpected change in online files")

            changed_roles.append(fname[:-len(".json")])

    # reorder, toplevels first
    for toplevel in ["targets", "root"]:
        if toplevel in changed_roles:
            changed_roles.remove(toplevel)
            changed_roles.insert(0, toplevel)

    return changed_roles


def _role_status(repo: PlaygroundRepository, role:str, event_name) -> bool:
    status, prev_status = repo.status(role)
    role_is_valid = status.valid
    sig_counts = f"{len(status.signed)}/{status.threshold}"
    signed = status.signed
    missing = status.missing

    if prev_status:
        role_is_valid = role_is_valid and prev_status.valid
        sig_counts = f"{sig_counts} ({len(prev_status.signed)}/{prev_status.threshold})"
        signed = signed | prev_status.signed
        missing = missing | prev_status.missing

    if status.invites:
        click.echo(f"#### :x: {role}")
        click.echo(f"{role} delegations have open invites ({', '.join(status.invites)}).")
        click.echo(f"Invitees can accept the invitations by running `playground-sign {event_name}`")
    elif role_is_valid:
        click.echo(f"#### :heavy_check_mark: {role}")
        click.echo(f"{role} is verified and signed by {sig_counts} signers ({', '.join(signed)}).")
    elif signed:
        click.echo(f"#### :x:{role}")
        click.echo(f"{role} is not yet verified. It is signed by {sig_counts} signers ({', '.join(signed)}).")
    else:
        click.echo(f"#### :x: {role}")
        click.echo(f"{role} is unsigned and not yet verified")

    if status.message:
        click.echo(f"**Error**: {status.message}")
    elif missing and not status.invites:
        click.echo(f"Still missing signatures from {', '.join(missing)}")
        click.echo(f"Signers can sign these changes by running `playground-sign {event_name}`")

    return role_is_valid and len(status.invites) == 0


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
def status(verbose: int) -> None:
    """Status markdown output tool for Repository Playground CI"""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    event_name = _git(["branch", "--show-current"]).stdout.strip()

    click.echo("### Current signing event state")
    click.echo(f"Event {event_name}")
    
    if not os.path.exists("metadata/root.json"):
        click.echo(f"Repository does not exist yet. Create one with `playground-delegate {event_name}`.")
        sys.exit(1)

    # Find the known-good commit
    head = _git(["rev-parse", "HEAD"]).stdout.strip()
    merge_base = _git(["merge-base", "origin/main", "HEAD"]).stdout.strip()
    if head == merge_base:
        click.echo("This signing event contains no changes yet")
        sys.exit(1)

    with TemporaryDirectory() as known_good_dir:
        _git(["clone", "--quiet", ".", known_good_dir])
        _git(["-C", known_good_dir, "checkout", "--quiet", merge_base])

        good_dir = os.path.join(known_good_dir, "metadata")
        success = True

        # Compare current repository and the known good version.
        # Print status for each role, count invalid roles
        repo = PlaygroundRepository("metadata", good_dir)
        for role in _find_changed_roles(good_dir, "metadata"):
            if not _role_status(repo, role, event_name):
                success = False

    sys.exit(0 if success else 1)
