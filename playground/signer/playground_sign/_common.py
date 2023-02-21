# Copyright 2023 Google LLC

"""Common helper functions"""

from configparser import ConfigParser
import subprocess
import click

from securesystemslib.signer import HSMSigner, Key

def get_signing_key_input(message: str) -> Key:
    # TODO use value_proc argument to validate the input
    click.prompt(message, default=True, show_default=False)
    try:
        _, key = HSMSigner.import_()
    except Exception as e:
        raise click.ClickException(f"Failed to read HW key: {e}")

    return key


def get_secret_input(secret: str, role: str) -> str:
    return click.prompt(f"Enter {secret} to sign {role}", hide_input=True)


def read_settings(config_path: str) -> tuple[str, str]:
    config = ConfigParser()
    config.read(config_path)
    # TODO: create config if missing, ask user for values
    if not config:
        raise click.ClickException(f"Settings file {config_path} not found")
    try:
        return config["settings"]["user-name"], config["settings"]["pykcs11lib"]
    except KeyError as e:
        raise click.ClickException(f"Failed to find required setting {e} in {config_path}")


def git(cmd: list[str]) -> str:
    cmd = ["git"] + cmd
    proc = subprocess.run(cmd, capture_output=True, check=True, text=True)
    return proc.stdout.strip()
