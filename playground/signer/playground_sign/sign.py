# Copyright 2023 Google LLC

"""playground-sign: A command line tool to sign Repository Playground changes"""

from tempfile import TemporaryDirectory
import click
import logging
import os

from playground_sign._common import (
    get_secret_input,
    git,
)
from playground_sign._signer_repository import (
    SignerRepository,
    SignerState,
)

logger = logging.getLogger(__name__)

@click.command()
@click.option("-v", "--verbose", count=True, default=0)
def sign(verbose: int):
    """Signing tool for Repository Playground signing events."""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    toplevel = git(["rev-parse", "--show-toplevel"])
    metadata_dir = os.path.join(toplevel, "metadata")
    settings_path = os.path.join(toplevel, ".playground-sign.ini")

    # checkout the starting point of this signing event
    known_good_sha = git(["merge-base", "origin/main", "HEAD"])
    with TemporaryDirectory() as known_good_dir:
        prev_dir = os.path.join(known_good_dir, "metadata")
        git(["clone", "--quiet", toplevel, known_good_dir])
        git(["-C", known_good_dir, "checkout", "--quiet", known_good_sha])

        repo = SignerRepository(metadata_dir, prev_dir, settings_path, get_secret_input)
        if repo.state == SignerState.UNINITIALIZED:
            click.echo("No metadata repository found")
            changed = False
        elif repo.state == SignerState.INVITED:
            click.echo(f"You have been invited to become a signer for role(s) {repo.invites}.")
            message = "To accept the invitation, please insert your HW key and press enter"
            click.prompt(message, default=True, show_default=False)
            try:
                key = repo.read_signing_key()
            except Exception as e:
                raise click.ClickException(f"Failed to read HW key: {e}")

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
        click.echo(
            "Done. Tool does not commit or push at the moment. Try\n"
            "  git add metadata\n"
            f"  git commit -m 'Signed by {repo.user_name}'\n"
            "  git push origin <signing_event>"
        )