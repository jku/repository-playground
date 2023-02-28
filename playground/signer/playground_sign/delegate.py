# Copyright 2023 Google LLC

"""playground-modify: A command line tool to modify Repository Playground delegations"""

from copy import deepcopy
import copy
from tempfile import TemporaryDirectory
from typing import Optional
import click
import logging
import os
from securesystemslib.signer import GCPSigner

from playground_sign._common import (
    get_signing_key_input,
    get_secret_input,
    git,
    read_settings,
)
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


def _init_repository(repo: SignerRepository) -> bool:
    click.echo("Creating a new Playground TUF repository")

    root_config = _get_offline_input("root", OfflineConfig([repo.user_name], 1, 365, 60))
    targets_config = _get_offline_input("targets", deepcopy(root_config))
    online_config = _get_online_input(OnlineConfig(None, None, 1, root_config.expiry_period))

    key = None
    if repo.user_name in root_config.signers or repo.user_name in targets_config.signers:
        key = get_signing_key_input("Insert your HW key and press enter")

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
        key = get_signing_key_input("Insert your HW key and press enter")

    repo.set_role_config(role, new_config, key)
    return True


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.argument("role", required=False)
def delegate(verbose: int, role: Optional[str]):
    """Tool for modifying Repository Playground delegations."""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    toplevel = git(["rev-parse", "--show-toplevel"])
    metadata_dir = os.path.join(toplevel, "metadata")
    settings_path = os.path.join(toplevel, ".playground-sign.ini")
    user_name, pykcs11lib =read_settings(settings_path)

    # PyKCS11 (Yubikey support) needs the module path
    # TODO: if config is not set, complain/ask the user?
    if "PYKCS11LIB" not in os.environ:
        os.environ["PYKCS11LIB"] = pykcs11lib

    # checkout the starting point of this signing event
    known_good_sha = git(["merge-base", "origin/main", "HEAD"])
    with TemporaryDirectory() as known_good_dir:
        prev_dir = os.path.join(known_good_dir, "metadata")
        git(["clone", "--quiet", toplevel, known_good_dir])
        git(["-C", known_good_dir, "checkout", "--quiet", known_good_sha])

        repo = SignerRepository(metadata_dir, prev_dir, user_name, get_secret_input)
        if repo.state == SignerState.UNINITIALIZED:
            changed = _init_repository(repo)
        elif role in ["timestamp", "snapshot"]:
            changed = _update_online_roles(repo)
        elif role:
            changed =  _update_offline_role(repo, role)
        else:
            raise click.UsageError("ROLE is required")

    if changed:
        click.echo(
            "Done. Tool does not commit or push at the moment. Try\n"
            "  git add metadata\n"
            f"  git commit -m 'Delegation change by {user_name}'\n"
            f"  git push origin <signing_event>"
        )