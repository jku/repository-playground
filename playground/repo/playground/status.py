# Copyright 2023 Google LLC

"""Command line signing event status output tool for Repository Playground CI"""

from contextlib import contextmanager
import filecmp
from glob import glob
import os
import sys
import click
import logging

from playground._playground_repository import PlaygroundRepository

logger = logging.getLogger(__name__)

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

@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.argument("known-good-dir")
def status_cli(verbose: int, known_good_dir: str) -> None:
    """Status markdown output tool for Repository Playground CI"""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    # Find signing event metadata: we expect tool to run in git top level dir
    signing_event_dir = "metadata"
    good_dir = os.path.join(known_good_dir, signing_event_dir)
    failures = 0

    repo = PlaygroundRepository(signing_event_dir, good_dir)
    for role in _find_changed_roles(good_dir, signing_event_dir):
        status, prev_status = repo.status(role)
        role_is_valid = status.valid
        if not role_is_valid:
            failures += 1
        sig_counts = f"{len(status.signed)}/{status.threshold}"
        signed = status.signed
        missing = status.missing

        if prev_status:
            role_is_valid = role_is_valid and prev_status.valid
            sig_counts = f"{sig_counts} ({len(prev_status.signed)}/{prev_status.threshold})"
            signed = signed | prev_status.signed
            missing = missing | prev_status.missing

        # TODO: get reasons for verify failure from repo, print that
        if role_is_valid:
            click.echo(f"#### :heavy_check_mark: {role}")
            click.echo(f"{role} is verified and signed by {sig_counts} signers ({', '.join(signed)}).")
        elif signed:
            click.echo(f"#### :x:{role}")
            click.echo(f"{role} is not yet verified. It is signed by {sig_counts} signers ({', '.join(signed)}).")
        else:
            click.echo(f"#### :x: {role}")
            click.echo(f"{role} is unsigned and not yet verified")
        if missing:
            click.echo(f"Still missing signatures from {', '.join(missing)}")
    
    sys.exit(failures)