# Copyright 2023 Google LLC

"""playground-modify: A command line tool to modify Repository Playground delegations"""

from copy import deepcopy
import copy
from urllib import parse
import click
import logging
import os
from securesystemslib.signer import GCPSigner, SigstoreKey, KEY_FOR_TYPE_AND_SCHEME

from playground_sign._common import (
    get_signing_key_input,
    git,
    git_echo,
    SignerConfig,
    signing_event,
)
from playground_sign._signer_repository import (
    OnlineConfig,
    OfflineConfig,
    SignerRepository,
    SignerState,
)


# sigstore is not a supported key by default
KEY_FOR_TYPE_AND_SCHEME[("sigstore-oidc", "Fulcio")] = SigstoreKey


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

def _get_repo_name(remote: str):
    url = parse.urlparse(git(["config", "--get", f"remote.{remote}.url"]))
    repo = url.path[:-len(".git")]
    # ssh-urls are relative URLs according to urllib: host is actually part of
    # path. We don't want the host part:
    _, _, repo = repo.rpartition(":")
    # http urls on the other hand are not relative: remove the leading /
    return repo.lstrip("/")

def _sigstore_import(pull_remote: str) -> list[ SigstoreKey]:
    # WORKAROUND: build sigstore key and uri here since there is no import yet
    issuer = "https://token.actions.githubusercontent.com"
    repo = _get_repo_name(pull_remote)

    # Create separate keys for the two workflows that need keys
    keys = []
    for workflow, keyid in [("snapshot.yml", "abcd"), ("version-bumps.yml", "efgh")]:
        id = f"https://github.com/{repo}/.github/workflows/{workflow}@refs/heads/main"
        key = SigstoreKey(keyid, "sigstore-oidc", "Fulcio", {"issuer": issuer, "identity": id})
        key.unrecognized_fields["x-playground-online-uri"] = "sigstore:"
        keys.append(key)
    return keys

def _get_online_input(
    config: OnlineConfig, user_config: SignerConfig
) -> OnlineConfig:
    config = copy.deepcopy(config)
    click.echo(f"\nConfiguring online roles")
    while True:
        keyuri = config.keys[0].unrecognized_fields["x-playground-online-uri"]
        choice = click.prompt(
            f" 1. Configure online key: {keyuri}\n"
            f" 2. Configure timestamp: Expires in {config.timestamp_expiry} days\n"
            f" 3. Configure snapshot: Expires in {config.snapshot_expiry} days\n"
            "Please choose an option or press enter to continue",
            type=click.IntRange(0, 3),
            default=0,
            show_default=False,
        )
        if choice == 0:
            break
        if choice == 1:
            # TODO use value_proc argument to validate the input
            key_id = click.prompt(
                "Press enter to use Sigstore, or enter a Google Cloud KMS key id",
                default=""
            )
            if key_id == "":
                config.keys = _sigstore_import(user_config.pull_remote)
            else:
                try:
                    uri, key = GCPSigner.import_(key_id)
                    key.unrecognized_fields["x-playground-online-uri"] = uri
                    config.keys = [key]
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


def _init_repository(repo: SignerRepository, user_config: SignerConfig) -> bool:
    click.echo("Creating a new Playground TUF repository")

    root_config = _get_offline_input("root", OfflineConfig([repo.user_name], 1, 365, 60))
    targets_config = _get_offline_input("targets", deepcopy(root_config))

    # As default we offer sigstore online key(s)
    keys = _sigstore_import(user_config.pull_remote)
    default_config = OnlineConfig(keys, 1, root_config.expiry_period)
    online_config = _get_online_input(default_config, user_config)

    key = None
    if repo.user_name in root_config.signers or repo.user_name in targets_config.signers:
        key = get_signing_key_input("Insert your HW key and press enter")

    repo.set_role_config("root", root_config, key)
    repo.set_role_config("targets", targets_config, key)
    repo.set_online_config(online_config)
    return True

def _update_online_roles(repo: SignerRepository, user_config: SignerConfig) -> bool:
    click.echo(f"Modifying online roles")

    config = repo.get_online_config()
    new_config = _get_online_input(config, user_config)
    if new_config == config:
        return False

    repo.set_online_config(new_config)
    return True

def _update_offline_role(repo: SignerRepository, role: str) -> bool:

    config = repo.get_role_config(role)
    if not config:
        # Non existent role
        click.echo(f"Creating a new delegation for {role}")
        new_config = _get_offline_input(role, OfflineConfig([repo.user_name], 1, 365, 60))
    else:
        click.echo(f"Modifying delegation for {role}")
        new_config = _get_offline_input(role, config)
        if new_config == config:
            return False

    key = None
    if repo.user_name in new_config.signers:
        key = get_signing_key_input("Insert your HW key and press enter")

    repo.set_role_config(role, new_config, key)
    return True


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=True)
@click.argument("event-name", metavar="SIGNING-EVENT")
@click.argument("role", required=False)
def delegate(verbose: int, push: bool, event_name: str, role: str | None):
    """Tool for modifying Repository Playground delegations."""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    toplevel = git(["rev-parse", "--show-toplevel"])
    settings_path = os.path.join(toplevel, ".playground-sign.ini")
    user_config = SignerConfig(settings_path)

    with signing_event(event_name, user_config) as repo:
        if repo.state == SignerState.UNINITIALIZED:
            changed = _init_repository(repo, user_config)
        else:
            if role is None:
                role = click.prompt("Enter name of role to modify")

            if role in ["timestamp", "snapshot"]:
                changed = _update_online_roles(repo, user_config)
            else:
                changed =  _update_offline_role(repo, role)

        if changed:
            git(["add", "metadata/"])
            if role:
                msg = f"'{role}' role/delegation change"
            else:
                msg = "Initial offline metadata"
            git(["commit", "-m", msg, "--", "metadata"])
            if push:
                msg = f"Press enter to push changes to {user_config.push_remote}/{event_name}"
                click.prompt(msg, default=True, show_default=False)
                git_echo(["push", "--progress", user_config.push_remote, f"HEAD:refs/heads/{event_name}"])
            else:
                # TODO: deal with existing branch?
                click.echo(f"Creating local branch {event_name}")
                git(["branch", event_name])
        else:
            click.echo("Nothing to do")
