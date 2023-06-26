# Copyright 2023 Google LLC

"""Command line signing event status output tool for Repository Playground CI"""

import filecmp
from glob import glob
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib import parse
import click
import logging

from playground._playground_repository import PlaygroundRepository, SigningEventState

logger = logging.getLogger(__name__)


def _git(cmd: list[str]) -> subprocess.CompletedProcess:
    cmd = [
        "git",
        "-c",
        "user.name=repository-playground",
        "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
    ] + cmd
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.debug("%s:\n%s", cmd, proc.stdout)
        return proc
    except subprocess.CalledProcessError as e:
        print("Git output on error:", e.stdout, e.stderr)
        raise e


def _find_changed_roles(known_good_dir: str, signing_event_dir: str) -> set[str]:
    # find the files that have changed or been added
    # TODO what about removed roles?

    files = glob("*.json", root_dir=signing_event_dir)
    changed_roles = set()
    for fname in files:
        if not os.path.exists(f"{known_good_dir}/{fname}") or not filecmp.cmp(
            f"{signing_event_dir}/{fname}", f"{known_good_dir}/{fname}", shallow=False
        ):
            if fname in ["timestamp.json", "snapshot.json"]:
                assert "Unexpected change in online files"

            changed_roles.add(fname[: -len(".json")])

    return changed_roles


def _find_changed_target_roles(
    known_good_targets_dir: str, targets_dir: str
) -> set[str]:
    files = (
        glob("*", root_dir=targets_dir)
        + glob("*/*", root_dir=targets_dir)
        + glob("*", root_dir=known_good_targets_dir)
        + glob("*/*", root_dir=known_good_targets_dir)
    )
    changed_roles = set()
    for filepath in files:
        f1 = os.path.join(targets_dir, filepath)
        f2 = os.path.join(known_good_targets_dir, filepath)
        if os.path.isdir(f1) and os.path.isdir(f2):
            continue

        try:
            if filecmp.cmp(f1, f2, shallow=False):
                continue
        except FileNotFoundError:
            pass

        # we've found a changed target, add the rolename to list. Handle "targets" as special case
        rolename, _, _ = filepath.rpartition(filepath)
        if not rolename:
            rolename = "targets"
        changed_roles.add(rolename)

    return changed_roles


def _role_status(repo: PlaygroundRepository, role: str, event_name) -> bool:
    status, prev_status = repo.status(role)
    role_is_valid = status.valid
    sig_counts = f"{len(status.signed)}/{status.threshold}"
    signed = status.signed
    missing = status.missing

    # Handle the additional status for the possible previous, known good root version:
    if prev_status:
        role_is_valid = role_is_valid and prev_status.valid
        sig_counts = f"{len(prev_status.signed)}/{prev_status.threshold} ({sig_counts})"
        signed = signed | prev_status.signed
        missing = missing | prev_status.missing

    if role_is_valid and not status.invites:
        emoji = "heavy_check_mark"
    else:
        emoji = "x"
    click.echo(f"#### :{emoji}: {role}")

    if status.invites:
        click.echo(
            f"{role} delegations have open invites ({', '.join(status.invites)})."
        )
        click.echo(
            f"Invitees can accept the invitations by running `playground-sign {event_name}`"
        )

    if not status.invites:
        if status.target_changes:
            click.echo(f"{role} contains following target file changes:")
            for target_state in status.target_changes:
                click.echo(f" * {target_state}")
            click.echo("")

        if role_is_valid:
            click.echo(
                f"{role} is verified and signed by {sig_counts} signers ({', '.join(signed)})."
            )
        elif signed:
            click.echo(
                f"{role} is not yet verified. It is signed by {sig_counts} signers ({', '.join(signed)})."
            )
        else:
            click.echo(f"{role} is unsigned and not yet verified")

        if missing:
            click.echo(f"Still missing signatures from {', '.join(missing)}")
            click.echo(
                f"Signers can sign these changes by running `playground-sign {event_name}`"
            )

    if status.message:
        click.echo(f"**Error**: {status.message}")

    return role_is_valid and not status.invites


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=True)
def status(verbose: int, push: bool) -> None:
    """Status markdown output tool for Repository Playground CI"""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    event_name = _git(["branch", "--show-current"]).stdout.strip()

    click.echo("### Current signing event state")
    click.echo(f"Event [{event_name}](../compare/{event_name})")

    if not os.path.exists("metadata/root.json"):
        click.echo(
            f"Repository does not exist yet. Create one with `playground-delegate {event_name}`."
        )
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

        good_metadata = os.path.join(known_good_dir, "metadata")
        good_targets = os.path.join(known_good_dir, "targets")
        success = True

        # Compare current repository and the known good version.
        # Print status for each role, count invalid roles
        repo = PlaygroundRepository("metadata", good_metadata)

        # first create a list of roles that have metadata changes, artifact changes or delegation invites
        roles = list(
            _find_changed_roles(good_metadata, "metadata")
            | _find_changed_target_roles(good_targets, "targets")
            | repo.state.roles_with_delegation_invites()
        )
        # reorder, toplevels first
        for toplevel in ["targets", "root"]:
            if toplevel in roles:
                roles.remove(toplevel)
                roles.insert(0, toplevel)

        # If artifact metadata needs an update, do that. Then output the roles current status
        for role in roles:
            if repo.update_targets(role):
                # metadata and target content are not in sync: make a commit with metadata changes
                msg = f"Update targets metadata for role {role}"
                _git(["commit", "-m", msg, "--", f"metadata/{role}.json"])

            if not _role_status(repo, role, event_name):
                success = False

    if push:
        _git(["push", "origin", event_name])

    sys.exit(0 if success else 1)
