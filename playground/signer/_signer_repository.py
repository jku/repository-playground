# Copyright 2010 Google LLC

"""Internal repository module for playground signer tool"""

from dataclasses import dataclass
from enum import Enum, unique
import subprocess
import click
import os
from datetime import datetime, timedelta
from typing import Callable
from securesystemslib.signer import Signature, Signer

from tuf.api.metadata import Key, Metadata, MetaFile, Root, Signed, Targets
from tuf.api.serialization.json import JSONSerializer
from tuf.repository import Repository

def unmodified_in_git(filepath: str) -> bool:
    """Return True if the file is in git, and does not have changes in index"""
    cmd = ["git", "ls-files", "--error-unmatch", "--", filepath]
    if subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) != 0:
        return False

    cmd = ["git", "diff", "--exit-code", "--no-patch", "--", filepath]
    return subprocess.call(cmd) == 0

@unique
class SignerState(Enum):
    NO_ACTION = 0,
    UNINITIALIZED = 1,


@dataclass
class OnlineConfig:
    key: Key | None
    uri: str | None
    timestamp_expiry: int
    snapshot_expiry: int


@dataclass
class OfflineConfig:
    invited_signers: list[str]
    threshold: int
    expiry_period: int
    signing_period: int


class SignerRepository(Repository):
    """A repository implementation for the signer tool"""

    def __init__(self, dir: str, user_name: str, signing_key_func: Callable[[], Key]):
        self._dir = dir
        self.user_name = user_name
        self.state = SignerState.NO_ACTION
        self.get_signing_key = signing_key_func

        if not os.path.exists(os.path.join(self._dir, "root.json")):
            self.state = SignerState.UNINITIALIZED

    def _get_filename(self, role: str) -> str:
        return os.path.join(self._dir, f"{role}.json")

    def _get_versioned_root_filename(self, version: int) -> str:
        return os.path.join(self._dir, "root_history", f"{version}.root.json")

    def _get_expiry(self, role: str) -> datetime:
        # TODO use custom metadata, see ../IMPLEMENTATION-NOTES.md
        return datetime.utcnow() + timedelta(days=365)

    def _get_keys(self, role: str, signed: Signed) -> list[Key]:
        """Return public keys for delegated role"""

        if role == "root":
            pass # use the Signed we have already
        elif role in ["timestamp", "snapshot", "targets"]:
            signed = self.open("root").signed
        else:
            signed = self.open("targets").signed

        r = signed.get_delegated_role(role)
        keys = []
        for keyid in r.keyids:
            try:
                keys.append(signed.get_key(keyid))
            except ValueError:
                pass
        return keys

    def _sign(self, role: str, md: Metadata, key: Key) -> None:
        def secret_handler(secret: str) -> str:
            return click.prompt(f"Enter {secret} to sign {role}", hide_input=True)

        signer = Signer.from_priv_key_uri("hsm:", key, secret_handler)
        md.sign(signer, True)

    def _write(self, role: str, md: Metadata) -> None:
        filename = self._get_filename(role)

        os.makedirs(os.path.join(self._dir, "root_history"), exist_ok=True)

        data = md.to_bytes(JSONSerializer())
        with open(filename, "wb") as f:
            f.write(data)

        # For root, also store the versioned metadata
        if role == "root":
            with open(self._get_versioned_root_filename(md.signed.version), "wb") as f:
                f.write(data)

    def open(self, role:str) -> Metadata:
        """Read metadata from repository directory, or create new metadata"""
        fname = self._get_filename(role)

        if not os.path.exists(fname):
            if role in ["snapshot", "timestamp"]:
                raise ValueError(f"Cannot create {role}")
            if role == "root":
                md = Metadata(Root())
            else:
                md = Metadata(Targets())
        else:
            with open(fname, "rb") as f:
                md = Metadata.from_bytes(f.read())

        return md

    def close(self, role: str, md: Metadata) -> None:
        """Write metadata to a file in the repository directory"""
        filename = self._get_filename(role)

        # Avoid bumping version within a single git commit
        # TODO this should maybe compare to the forking point of this signing event
        # and bump version only once within the signing event
        if unmodified_in_git(filename):
            md.signed.version += 1

        md.signed.expires = self._get_expiry(role)

        md.signatures.clear()
        for key in self._get_keys(role, md.signed):
            keyowner = key.unrecognized_fields["x-playground-keyowner"]
            if keyowner == self.user_name:
                self._sign(role, md, key)
            else:
                # another offline signer: add empty signature
                md.signatures[key.keyid] = Signature(key.keyid, "")

        self._write(role, md)

    # NOTE: python-tuf should be changed so these are not required
    @property
    def targets_infos(self) -> dict[str, MetaFile]:
        raise NotImplementedError

    @property
    def snapshot_info(self) -> MetaFile:
        raise NotImplementedError

    def initialize(
        self, root_config: OfflineConfig, targets_config: OfflineConfig, online_config: OnlineConfig
    ):
        if self.user_name in root_config.invited_signers or self.user_name in targets_config.invited_signers:
            signing_key = self.get_signing_key()
            signing_key.unrecognized_fields["x-playground-keyowner"] = self.user_name

        online_config.key.unrecognized_fields["x-playground-online-uri"] = online_config.uri

        # Create root metadata
        with self.edit("root") as root:
            root.unrecognized_fields["x-playground-expiry-period"] = root_config.expiry_period
            root.unrecognized_fields["x-playground-signing-period"] = root_config.signing_period

            # Add online keys (and user key if they are invited)
            root.add_key(online_config.key, "timestamp")
            root.add_key(online_config.key, "snapshot")
            if self.user_name in root_config.invited_signers:
                root.add_key(signing_key, "root")
                root_config.invited_signers.remove(self.user_name)
            if self.user_name in targets_config.invited_signers:
                root.add_key(signing_key, "targets")
                targets_config.invited_signers.remove(self.user_name)

            # Invite signers
            if root_config.invited_signers:
                root.roles["root"].unrecognized_fields[
                    "x-playground-invited-signers"
                ] = targets_config.invited_signers
            root.roles["root"].threshold = root_config.threshold
            if targets_config.invited_signers:
                root.roles["targets"].unrecognized_fields[
                    "x-playground-invited-signers"
                ] = targets_config.invited_signers
            root.roles["targets"].threshold = targets_config.threshold

            # set online role periods
            root.roles["timestamp"].unrecognized_fields[
                "x-playground-expiry-period"
            ] = online_config.timestamp_expiry
            root.roles["snapshot"].unrecognized_fields[
                "x-playground-expiry-period"
            ] = online_config.snapshot_expiry

        # Create Targets metadata
        with self.edit("targets") as targets:
            targets.unrecognized_fields["x-playground-expiry-period"] = targets_config.expiry_period
            targets.unrecognized_fields["x-playground-signing-period"] = targets_config.expiry_period
