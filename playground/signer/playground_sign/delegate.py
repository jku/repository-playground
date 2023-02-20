# Copyright 2023 Google LLC

"""playground-modify: A command line tool to modify Repository Playground delegations"""

from copy import deepcopy
import copy
import random
import string
import subprocess
import click
from configparser import ConfigParser
import logging
import os
from securesystemslib.signer import GCPSigner, HSMSigner, Key

from playground_sign._signer_repository import (
    OnlineConfig,
    OfflineConfig,
    SignerRepository,
    SignerState,
)

logger = logging.getLogger(__name__)

def _get_offline_input(
    role: str,
    config: OfflineConfig,
) -> OfflineConfig:
    config = copy.deepcopy(config)
    click.echo(f"\nConfiguring role {role}")
    while True:
        choice = click.prompt(
            f" 1. Configure signers: [{', '.join(config.signers)}], requiring {config.threshold} signatures\n"
            f" 2. Configure expiry: Role expires in {config.expiry_period} days, re-signing starts {config.signing_period} days before expiry\n"
            "Please choose an option or press enter to continue",
            type=click.IntRange(0, 2),
            default=0,
            show_default=False,
        )
        if choice == 0:
            break
        if choice == 1:
            # TODO use value_proc argument to validate the input
            response = click.prompt(
                f"Please enter list of {role} signers",
                default=", ".join(config.signers)
            )
            config.signers.clear()
            for s in response.split(","):
                s = s.strip()
                if not s.startswith("@"):
                    s = f"@{s}"
                config.signers.append(s)

            if len(config.signers) == 1:
                config.threshold = 1
            else:
                # TODO use value_proc argument to validate threshold is [1-len(new_signers)]
                config.threshold = click.prompt(
                    f"Please enter {role} threshold",
                    type=int,
                    default=config.threshold
                )
        elif choice == 2:
            config.expiry_period = click.prompt(
                f"Please enter {role} expiry period in days",
                type=int,
                default=config.expiry_period,
            )
            config.signing_period = click.prompt(
                f"Please enter {role} signing period in days",
                type=int,
                default=config.signing_period,
            )

    return config


def _get_online_input(
    config: OnlineConfig
) -> OnlineConfig:
    config = copy.deepcopy(config)
    click.echo(f"\nConfiguring online roles")
    while True:
        choice = click.prompt(
            f" 1. Configure KMS key: {config.uri}\n"
            f" 2. Configure timestamp: Expires in {config.timestamp_expiry} days\n"
            f" 3. Configure snapshot: Expires in {config.snapshot_expiry} days\n"
            "Please choose an option or press enter to continue",
            type=click.IntRange(0, 3),
            default=0,
            show_default=False,
        )
        if choice == 0:
            if not config.uri:
                click.secho("Error: Missing KMS key", fg="red")
            else:
                break
        if choice == 1:
            # TODO use value_proc argument to validate the input
            gcp_key_id = click.prompt(
                "Please enter the Google Cloud KMS key id to use for online signing"
            )
            try:
                config.uri, config.key = GCPSigner.import_(gcp_key_id)
            except Exception as e:
                raise click.ClickException(f"Failed to read Google Cloud KMS key: {e}")
        if choice == 2:
            config.timestamp_expiry = click.prompt(
                f"Please enter timestamp expiry in days",
                type=int,
                default=config.timestamp_expiry,
            )
        if choice == 3:
            config.snapshot_expiry = click.prompt(
                f"Please enter snapshot expiry in days",
                type=int,
                default=config.snapshot_expiry,
            )

    return config


def _get_signing_key_input() -> Key:
    # TODO use value_proc argument to validate the input
    click.prompt(
        f"Insert your HW key and press enter",
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

def _init_repository(repo: SignerRepository) -> bool:
    click.echo("Creating a new Playground TUF repository")

    root_config = _get_offline_input("root", OfflineConfig([repo.user_name], 1, 365, 60))
    targets_config = _get_offline_input("targets", deepcopy(root_config))
    online_config = _get_online_input(OnlineConfig(None, None, 1, root_config.expiry_period))

    key = None
    if repo.user_name in root_config.signers or repo.user_name in targets_config.signers:
        key = _get_signing_key_input()

    repo.set_role_config("root", root_config, key)
    repo.set_role_config("targets", targets_config, key)
    repo.set_online_config(online_config)
    return True

def _update_online_roles(repo) -> bool:
    click.echo(f"Modifying online roles")

    config = repo.get_online_config()
    new_config = _get_online_input(config)
    if new_config == config:
        return False

    repo.set_online_config(new_config)
    return True

def _update_offline_role(repo: SignerRepository, role: str) -> bool:
    click.echo(f"Modifying delegation for {role}")

    config = repo.get_role_config(role)
    new_config = _get_offline_input(role, config)
    if new_config == config:
        return False

    key = None
    if repo.user_name in config.signers:
        key = _get_signing_key_input()

    repo.set_role_config(role, new_config, key)
    return True


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.argument("signing-event")
@click.argument("role", required=False)
def delegate(verbose: int, signing_event: str, role: str | None):
    """Tool for modifying Repository Playground delegations."""
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
        changed = _init_repository(repo)
    elif role in ["timestamp", "snapshot"]:
        changed = _update_online_roles(repo)
    elif role:
        changed =  _update_offline_role(repo, role)
    else:
        raise click.UsageError("ROLE is required")

    if changed:
        try:
            _git(["add", metadata_dir])
            _git(["commit", "-m", f"Changes for {signing_event}"])
            _push(signing_event, settings["pull-remote"], settings["push-remote"], branch)
        except subprocess.CalledProcessError as e:
            click.echo(f"Error: {e.stderr}")