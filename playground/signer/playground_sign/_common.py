# Copyright 2023 Google LLC

"""Common helper functions"""

from configparser import ConfigParser
from contextlib import contextmanager
import os
import subprocess
from tempfile import TemporaryDirectory
from typing import Generator
import click

from securesystemslib.signer import HSMSigner, Key

from playground_sign._signer_repository import SignerRepository

class SignerConfig:
    def __init__(self, path: str):
        config = ConfigParser()
        config.read(path)

        # TODO: create config if missing, ask/confirm values from user
        if not config:
            raise click.ClickException(f"Settings file {path} not found")
        try:
            self.user_name = config["settings"]["user-name"]
            self.pykcs11lib = config["settings"]["pykcs11lib"]
            self.push_remote = config["settings"]["push-remote"]
            self.pull_remote = config["settings"]["pull-remote"]
        except KeyError as e:
            raise click.ClickException(f"Failed to find required setting {e} in {path}")


@contextmanager
def signing_event(name: str, config: SignerConfig) -> Generator[SignerRepository, None, None]:
    toplevel = git(["rev-parse", "--show-toplevel"])

    # PyKCS11 (Yubikey support) needs the module path
    # TODO: if config is not set, complain/ask the user?
    if "PYKCS11LIB" not in os.environ:
        os.environ["PYKCS11LIB"] = config.pykcs11lib

    # first, make sure we're up-to-date
    git(["fetch", config.pull_remote])
    try:
        git(["checkout", f"{config.pull_remote}/{name}"])
    except subprocess.CalledProcessError:
        click.echo("Remote branch not found: branching off from main")
        git(["checkout", f"{config.pull_remote}/main"])

    try:
        # checkout the base of this signing event in another directory
        with TemporaryDirectory() as temp_dir:
            base_sha = git(["merge-base", f"{config.pull_remote}/main", "HEAD"])
            git(["clone", "--quiet", toplevel, temp_dir])
            git(["-C", temp_dir, "checkout", "--quiet", base_sha])
            base_metadata_dir = os.path.join(temp_dir, "metadata")
            metadata_dir = os.path.join(toplevel, "metadata")

            repo = SignerRepository(metadata_dir, base_metadata_dir, config.user_name, get_secret_input)
            yield repo
    finally:
        # go back to original branch
        git(["checkout", "-"])


def get_signing_key_input(message: str) -> Key:
    # TODO use value_proc argument to validate the input
    click.prompt(message, default=True, show_default=False)
    try:
        _, key = HSMSigner.import_()
    except Exception as e:
        raise click.ClickException(f"Failed to read HW key: {e}")

    return key


def get_secret_input(secret: str, role: str) -> str:
    msg = f"Enter {secret} to sign {role}"
    return click.prompt(msg, hide_input=True, show_default=False)


def git(cmd: list[str]) -> str:
    cmd = ["git"] + cmd
    proc = subprocess.run(cmd, capture_output=True, check=True, text=True)
    return proc.stdout.strip()

def git_echo(cmd: list[str]):
    cmd = ["git"] + cmd
    subprocess.run(cmd, check=True, text=True)