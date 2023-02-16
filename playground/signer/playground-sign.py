#!/usr/bin/env python

from copy import deepcopy
import subprocess
import click
from configparser import ConfigParser
import logging
import os
from securesystemslib.signer import GCPSigner, HSMSigner, Key

from _signer_repository import OnlineConfig, OfflineConfig, SignerRepository, SignerState

logger = logging.getLogger(__name__)

def _get_offline_input(
    role: str,
    config: OfflineConfig,
) -> OfflineConfig:
    while True:
        choice = click.prompt(
            f"\nConfiguring role {role}\n"
            f" 1. Configure signers: {config.invited_signers}, requiring {config.threshold} signatures\n"
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
                f"Please enter list of {role} signers", default=str(config.invited_signers)
            )
            config.invited_signers.clear()
            for s in response.split(","):
                s = s.strip()
                if not s.startswith("@"):
                    s = f"@{s}"
                config.invited_signers.append(s)

            if len(config.invited_signers) == 1:
                config.threshold = 1
            else:
                # TODO use value_proc argument to validate threshold is [1-len(new_signers)]
                config.threshold = click.prompt(
                    f"Please enter {role} threshold", type=int, default=config.threshold
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
    # TODO make this use existing key as the default value
    
    while True:
        choice = click.prompt(
            f"\nConfiguring online roles\n"
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
        "Insert HW key to use as initial root and targets key and press enter",
        default=True,
        show_default=False,
    )
    try:
        _, key = HSMSigner.import_()
    except Exception as e:
        raise click.ClickException(f"Failed to read HW key: {e}")

    return key


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
def cli(verbose: int):
    """Signing tool for repository-playground."""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    cmd = ["git", "rev-parse", "--show-toplevel"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, check=True, text=True)
    toplevel = proc.stdout.strip()
    metadata_dir = os.path.join(toplevel, "metadata")

    # TODO: check that this is a playground repository,
    # so we don't start creating metadata in random git repos

    config = ConfigParser()
    config.read(os.path.join(toplevel, ".playground-sign.ini"))

    # TODO: create config if missing, ask user for values
    if not config or "settings" not in config:
        raise RuntimeError("Settings file not found")

    # PyKCS11 (Yubikey support) needs the module path
    # TODO: if config is not set, complain/ask the user?
    if "PYKCS11LIB" not in os.environ and "pykcs11lib" in config["settings"]:
        os.environ["PYKCS11LIB"] = config["settings"]["pykcs11lib"]

    # TODO: if config is not set, complain/ask the user?
    user_name = config["settings"]["user-name"]

    repo = SignerRepository(metadata_dir, user_name, _get_signing_key_input)
    if repo.state == SignerState.UNINITIALIZED:
        click.echo("Creating a new Playground TUF repository")

        root_config = _get_offline_input("root", OfflineConfig([repo.user_name], 1, 365, 60))
        targets_config = _get_offline_input("targets", deepcopy(root_config))
        online_config = _get_online_input(OnlineConfig(None, None, 1, root_config.expiry_period))

        logger.debug("Root input: %s", root_config)
        logger.debug("Targets input: %s",targets_config)
        logger.debug("Online input: %s", online_config)

        repo.initialize(root_config, targets_config, online_config)
    else:
        click.echo("Nothing to do.")

if __name__ == "__main__":
    cli()
