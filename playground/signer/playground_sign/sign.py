# Copyright 2023 Google LLC

"""playground-sign: A command line tool to sign Repository Playground changes"""

from tempfile import TemporaryDirectory
import click
import logging
import os

from playground_sign._common import (
    get_signing_key_input,
    get_secret_input,
    git,
    SignerConfig,
)
from playground_sign._signer_repository import (
    SignerRepository,
    SignerState,
)

logger = logging.getLogger(__name__)

@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=True)
@click.argument("signing-event")
def sign(verbose: int, push: bool, signing_event: str):
    """Signing tool for Repository Playground signing events."""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    toplevel = git(["rev-parse", "--show-toplevel"])
    settings_path = os.path.join(toplevel, ".playground-sign.ini")
    config = SignerConfig(settings_path)

    # first, checkout current signing event branch
    git(["fetch", config.pull_remote])
    git(["checkout", f"{config.pull_remote}/{signing_event}"])
    # TODO: wrap everything after checkout inside a try-finally so that
    # we can undo checkout in "finally" even if something goes wrong.

    metadata_dir = os.path.join(toplevel, "metadata")

    # PyKCS11 (Yubikey support) needs the module path
    # TODO: if config is not set, complain/ask the user?
    if "PYKCS11LIB" not in os.environ:
        os.environ["PYKCS11LIB"] = config.pykcs11lib

    # checkout the starting point of this signing event
    known_good_sha = git(["merge-base", f"{config.pull_remote}/main", "HEAD"])
    with TemporaryDirectory() as known_good_dir:
        prev_dir = os.path.join(known_good_dir, "metadata")
        git(["clone", "--quiet", toplevel, known_good_dir])
        git(["-C", known_good_dir, "checkout", "--quiet", known_good_sha])

        repo = SignerRepository(metadata_dir, prev_dir, config.user_name, get_secret_input)
        if repo.state == SignerState.UNINITIALIZED:
            click.echo("No metadata repository found")
            changed = False
        elif repo.state == SignerState.INVITED:
            click.echo(f"You have been invited to become a signer for role(s) {repo.invites}.")
            key = get_signing_key_input("To accept the invitation, please insert your HW key and press enter")
            for rolename in repo.invites.copy():
                # Modify the delegation
                config = repo.get_role_config(rolename)
                repo.set_role_config(rolename, config, key)

                # Sign the role we are now a signer for
                if rolename != "root":
                    repo.sign(rolename)

            # Sign any other roles we may be asked to sign at the same time
            if repo.unsigned:
                click.echo(f"Your signature is requested for role(s) {repo.unsigned}.")
                for rolename in repo.unsigned:
                    click.echo(repo.status(rolename))
                    repo.sign(rolename)
            changed = True
        elif repo.state == SignerState.SIGNATURE_NEEDED:
            click.echo(f"Your signature is requested for role(s) {repo.unsigned}.")
            for rolename in repo.unsigned:
                click.echo(repo.status(rolename))
                repo.sign(rolename)
            changed = True
        elif repo.state == SignerState.TARGETS_CHANGED:
            click.echo(f"Following local target files changes have been found:")
            for rolename, states in repo.target_changes.items():
                for target_state in states.values():
                    click.echo(f"  {target_state.target.path} ({target_state.state.name})")
            click.prompt("Press enter to approve these changes", default=True, show_default=False)

            repo.update_targets()
            changed = True
        elif repo.state == SignerState.NO_ACTION:
            changed = False
        else:
            raise NotImplementedError

    if changed:
        git(["commit", "-m", f"Signed by {config.user_name}", "--", "metadata"])
        if push:
            msg = f"Press enter to push signature(s) to {config.push_remote}/{signing_event}"
            click.prompt(msg, default=True, show_default=False)
            git(["push", config.push_remote, f"HEAD:refs/heads/{signing_event}"])
            click.echo(f"Pushed branch {signing_event} to {config.push_remote}")
        else:
            # TODO: maybe deal with existing branch?
            click.echo(f"Creating local branch {signing_event}")
            git(["branch", signing_event])
    else:
        click.echo("Nothing to do.")

    git(["checkout", "-"])