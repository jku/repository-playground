# Copyright 2023 Google LLC

"""playground-sign: A command line tool to sign Repository Playground changes"""

import random
import string
import subprocess
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


def _checkout(remote: str, branch: str) -> str:
    # TODO prepare for all kinds of mistakes:
    # branch not existing, local branch having conflicts, current branch having changes...
    _git(["fetch", remote, branch])

    # we want a new branch that does not exist
    rand_s = ''.join(random.choices(string.ascii_letters + string.digits, k=7))
    new_branch = f"{branch}-{rand_s}"
    _git(["checkout", "--track", "-b", new_branch, f"{remote}/{branch}"])
    return new_branch


def _push(signing_event: str, pull_remote: str, push_remote: str, branch: str):
     # push to signing event branch if we can push there
    if pull_remote == push_remote:
        _git(["push", push_remote, f"{branch}:{signing_event}"])
        click.echo(f"{signing_event} updated")
    else:
        _git(["push", push_remote, f"{branch}:{branch}"])
        # TODO: Unsure how to build this hard coded URL easily... maybe parsing "git config --get remote.{remote}.url"?
        # maybe should add configuration for project name?
        click.echo(
            f"Create a pull request for {signing_event} on GitHub by visiting:\n"
            f"    https://github.com/jku/test-repo-for-playground/compare/{signing_event}...{branch}?expand=1"
        )


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.argument("signing-event")
def sign(verbose: int, signing_event: str):
    """Signing tool for Repository Playground signing events."""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    toplevel = _git(["rev-parse", "--show-toplevel"])
    metadata_dir = os.path.join(toplevel, "metadata")

    # TODO: check that this is a playground repository,
    # so we don't start creating metadata in random git repos

    settings = _read_settings(os.path.join(toplevel, ".playground-sign.ini"))

    # TODO support not-doing-network-ops
    # TODO: maybe do this in a temp dir to avoid messing the users git env (see error handling later)
    # The issue with this is that it hides the git changes from user who might want to look at them
    branch = _checkout(settings["pull-remote"], signing_event)

    # PyKCS11 (Yubikey support) needs the module path
    # TODO: if config is not set, complain/ask the user?
    if "PYKCS11LIB" not in os.environ and "pykcs11lib" in settings:
        os.environ["PYKCS11LIB"] = settings["pykcs11lib"]

    # TODO: if config is not set, complain/ask the user?
    user_name = settings["user-name"]

    repo = SignerRepository(metadata_dir, user_name, _get_secret_input)
    if repo.state == SignerState.UNINITIALIZED:
        raise click.UsageError("No metadata repository found")
    elif repo.state == SignerState.INVITED:
        click.echo(f"You have been invited to become a signer for role(s) {repo.invites}.")
        key = _get_signing_key_input()
        for rolename in repo.invites:
            config = repo.get_role_config(rolename)
            repo.set_role_config(rolename, config, key)
        if repo.unsigned:
            click.echo(f"Your signature is requested for role(s) {repo.unsigned}.")
            for rolename in repo.unsigned:
                click.echo(repo.status(rolename))
                repo.sign(rolename)

    elif repo.state == SignerState.SIGNATURE_NEEDED:
        click.echo(f"Your signature is requested for role(s) {repo.unsigned}.")
        for rolename in repo.unsigned:
            click.echo(repo.status(rolename))
            repo.sign(rolename)
    else:
        raise NotImplementedError

    try:
        _git(["add", metadata_dir])
        _git(["commit", "-m", f"Changes for {signing_event}"])
        _push(signing_event, settings["pull-remote"], settings["push-remote"], branch)
    except subprocess.CalledProcessError as e:
        click.echo(f"Error: {e.stderr}")
