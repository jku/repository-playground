# Copyright 2023 Google LLC

"""Command line signing event status update tool for Repository Playground CI"""

import filecmp
from glob import glob
import os
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

# TODO is good dir needed here?

@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.argument("known-good-dir")
def request_signatures(verbose: int, known_good_dir: str) -> None:
    """Signing event status update tool for Repository Playground CI
    
    This command modifies the .signing-event-state file, adding signing requests for
    * signers of roles that have changed in this signing event
    * if the signer has not signed yet
    """
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    repo = PlaygroundRepository("metadata", good_dir)
    for role in _find_changed_roles(good_dir, signing_event_dir):
        repo.request_signatures(role)
