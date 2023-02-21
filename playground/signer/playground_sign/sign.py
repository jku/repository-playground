# Copyright 2023 Google LLC

"""playground-sign: A command line tool to sign Repository Playground changes"""

import random
import string
import subprocess
from tempfile import TemporaryDirectory
import click
from configparser import ConfigParser
import logging
import os
from securesystemslib.signer import HSMSigner, Key

from playground_sign._signer_repository import (
    SignerRepository,
    SignerState,
)

logger = logging.getLogger(__name__)


def _get_signing_key_input() -> Key:
    # TODO use value_proc argument to validate the input
    click.prompt(
        "To accept the invitation, please insert your HW key and press enter",
        default=True,
        show_default=False,
    )
    try:
        _, key = HSMSigner.import_()
    except Exception as e:
        raise click.ClickException(f"Failed to read HW key: {e}")

    return key


def _get_secret_input(secret: str, role: str) -> str:
    return click.prompt(f"Enter {secret} to sign {role}", hide_input=True)


def _read_settings(config_path: str) -> dict[str, str]:
    config = ConfigParser()
    config.read(config_path)
    # TODO: create config if missing, ask user for values
    if not config or "settings" not in config:
        raise RuntimeError("Settings file not found")
    return config["settings"]


def _git(cmd: list[str]) -> str:
    cmd = ["git"] + cmd
    proc = subprocess.run(cmd, capture_output=True, check=True, text=True)
    return proc.stdout.strip()


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
def sign(verbose: int):
    """Signing tool for Repository Playground signing events."""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    toplevel = _git(["rev-parse", "--show-toplevel"])
    metadata_dir = os.path.join(toplevel, "metadata")
    settings = _read_settings(os.path.join(toplevel, ".playground-sign.ini"))

    # PyKCS11 (Yubikey support) needs the module path
    # TODO: if config is not set, complain/ask the user?
    if "PYKCS11LIB" not in os.environ and "pykcs11lib" in settings:
        os.environ["PYKCS11LIB"] = settings["pykcs11lib"]

    # TODO: if config is not set, complain/ask the user?
    user_name = settings["user-name"]

    # checkout the starting point of this signing event
    known_good_sha = _git(["merge-base", "origin/main", "HEAD"])
    with TemporaryDirectory() as known_good_dir:
        _git(["clone", "--quiet", toplevel, known_good_dir])
        _git(["-C", known_good_dir, "checkout", "--quiet", known_good_sha])

        repo = SignerRepository(metadata_dir, known_good_dir, user_name, _get_secret_input)
        if repo.state == SignerState.UNINITIALIZED:
            click.echo("No metadata repository found")
            changed = False
        elif repo.state == SignerState.INVITED:
            click.echo(f"You have been invited to become a signer for role(s) {repo.invites}.")
            key = _get_signing_key_input()
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
        elif repo.state == SignerState.NO_ACTION:
            changed = False
        else:
            raise NotImplementedError

    if changed:
        click.echo(
            "Done. Tool does not commit or push at the moment. Try\n"
            "  git add metadata\n"
            f"  git commit -m 'Signed by {user_name}'\n"
            "  git push origin <signing_event>"
        )