# Copyright 2023 Google LLC

"""Common helper functions"""

import subprocess
import click

from securesystemslib.signer import HSMSigner, Key


def get_secret_input(secret: str, role: str) -> str:
    return click.prompt(f"Enter {secret} to sign {role}", hide_input=True)


def git(cmd: list[str]) -> str:
    cmd = ["git"] + cmd
    proc = subprocess.run(cmd, capture_output=True, check=True, text=True)
    return proc.stdout.strip()
