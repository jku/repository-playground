# Copyright 2023 Google LLC

"""Common helper functions"""

from configparser import ConfigParser
import subprocess
import click

from securesystemslib.signer import HSMSigner, Key

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
            self.push_remote = config["settings"]["pull-remote"]
            self.pull_remote = config["settings"]["push-remote"]
        except KeyError as e:
            raise click.ClickException(f"Failed to find required setting {e} in {path}")

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
