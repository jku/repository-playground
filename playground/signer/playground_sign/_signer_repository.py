# Copyright 2023 Google LLC

"""Internal repository module for playground signer tool"""

from dataclasses import dataclass
from enum import Enum, unique
import json
import subprocess
import os
from datetime import datetime, timedelta
from typing import Callable
from securesystemslib.exceptions import UnverifiedSignatureError
from securesystemslib.signer import Signature, Signer

from tuf.api.metadata import Key, Metadata, MetaFile, Root, Targets
from tuf.api.serialization.json import CanonicalJSONSerializer, JSONSerializer
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
    INVITED = 2,
    SIGNATURE_NEEDED = 3,


@dataclass
class OnlineConfig:
    key: Key | None
    uri: str | None
    timestamp_expiry: int
    snapshot_expiry: int


@dataclass
class OfflineConfig:
    signers: list[str]
    threshold: int
    expiry_period: int
    signing_period: int


class SignerRepository(Repository):
    """A repository implementation for the signer tool"""

    def __init__(self, dir: str, user_name: str, secret_func: Callable[[str, str], str]):
        self.user_name = user_name
        self._dir = dir
        self._get_secret = secret_func
        self._state_config = {"invites": {}, "unsigned": {}}

        # read signing event state file
        state_file = os.path.join(self._dir, ".signing-event-state")
        if os.path.exists(state_file):
            with open(state_file) as f:
                self._state_config  = json.load(f)

        # Find current state
        if not os.path.exists(os.path.join(self._dir, "root.json")):
            self.state = SignerState.UNINITIALIZED
        elif self.invites:
            self.state = SignerState.INVITED
        elif self.unsigned:
            self.state = SignerState.SIGNATURE_NEEDED
        else:
            self.state = SignerState.NO_ACTION

    @property
    def invites(self) -> list[str]:
        try:
            return self._state_config["invites"][self.user_name]
        except KeyError:
            return []

    @property
    def unsigned(self) -> list[str]:
        try:
            return self._state_config["unsigned"][self.user_name]
        except KeyError:
            return []

    def _user_signature_needed(self, rolename: str) -> bool:
        md = self.open(rolename)
        for key in self._get_keys(rolename):
            keyowner = key.unrecognized_fields["x-playground-keyowner"]
            if keyowner == self.user_name:
                try:
                    payload = CanonicalJSONSerializer().serialize(md.signed)
                    key.verify_signature(md.signatures[key.keyid], payload)
                except (KeyError, UnverifiedSignatureError):
                    return True
        return False

    def _get_filename(self, role: str) -> str:
        return os.path.join(self._dir, f"{role}.json")

    def _get_versioned_root_filename(self, version: int) -> str:
        return os.path.join(self._dir, "root_history", f"{version}.root.json")

    def _get_expiry(self, role: str) -> datetime:
        # TODO use custom metadata, see ../IMPLEMENTATION-NOTES.md
        return datetime.utcnow() + timedelta(days=365)

    def _get_keys(self, role: str) -> list[Key]:
        """Return public keys for delegated role"""
        if role in ["root", "timestamp", "snapshot", "targets"]:
            delegator: Root|Targets = self.open("root").signed
        else:
            delegator = self.open("targets").signed

        r = delegator.get_delegated_role(role)
        keys = []
        for keyid in r.keyids:
            try:
                keys.append(delegator.get_key(keyid))
            except ValueError:
                pass
        return keys

    def _sign(self, role: str, md: Metadata, key: Key) -> None:
        def secret_handler(secret: str) -> str:
            return self._get_secret(secret, role)

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
        # TODO this should compare to the forking point of this signing event
        # and bump version only once within the signing event
        # status() requires the comparison anyway so should not be a problem?
        if unmodified_in_git(filename):
            md.signed.version += 1

        md.signed.expires = self._get_expiry(role)

        md.signatures.clear()
        for key in self._get_keys(role):
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

    def get_online_config(self) -> OnlineConfig:
        """Read configuration for online delegation from metadata"""
        root: Root = self.open("root").signed

        timestamp_role = root.get_delegated_role("timestamp")
        snapshot_role = root.get_delegated_role("snapshot")
        timestamp_expiry = timestamp_role.unrecognized_fields["x-playground-expiry-period"]
        snapshot_expiry = snapshot_role.unrecognized_fields["x-playground-expiry-period"]
        key = root.get_key(timestamp_role.keyids[0])
        uri = key.unrecognized_fields["x-playground-online-uri"]

        return OnlineConfig(key, uri, timestamp_expiry, snapshot_expiry)

    def set_online_config(self, online_config: OnlineConfig):
        """Store online delegation configuration in metadata."""
        online_config.key.unrecognized_fields["x-playground-online-uri"] = online_config.uri

        with self.edit("root") as root:
            # Add online keys
            root.add_key(online_config.key, "timestamp")
            root.add_key(online_config.key, "snapshot")

            # set online role periods
            role = root.get_delegated_role("timestamp")
            role.unrecognized_fields["x-playground-expiry-period"] = online_config.timestamp_expiry
            role = root.get_delegated_role("snapshot")
            role.unrecognized_fields["x-playground-expiry-period"] = online_config.snapshot_expiry

    def get_role_config(self, rolename: str) -> OfflineConfig:
        """Read configuration for delegation and role from metadata"""
        if rolename in ["timestamp", "snapshot"]:
            raise ValueError("online roles not supported")

        md = self.open(rolename)
        if rolename == "root":
            delegator:Metadata[Root|Targets] = md
        elif rolename == "targets":
            delegator = self.open("root")
        else:
            delegator = self.open("targets")
        role = delegator.signed.get_delegated_role(rolename)

        expiry = md.signed.unrecognized_fields["x-playground-expiry-period"]
        signing = md.signed.unrecognized_fields["x-playground-signing-period"]
        threshold = role.threshold
        signers = []
        # Include current invitees on config
        for signer, rolenames in self._state_config["invites"].items():
            if rolename in rolenames:
                signers.append(signer)
        # Include current signers on config
        for keyid in role.keyids:
            try:
                key = delegator.signed.get_key(keyid)
                signers.append(key.unrecognized_fields["x-playground-keyowner"])
            except ValueError:
                pass

        return OfflineConfig(signers, threshold, expiry, signing)

    def set_role_config(self, rolename: str, config: OfflineConfig, signing_key: Key | None):
        """Store delegation & role configuration in metadata.

        signing_key is only used if user is configured as signer"""
        if rolename in ["timestamp", "snapshot"]:
            raise ValueError("online roles not supported")

        if rolename in ["root", "targets"]:
            delegator_name = "root"
        else:
            delegator_name = "targets"

        # TODO only save new version if values change
        with self.edit(delegator_name) as delegator:
            # Handle existing signers
            role = delegator.get_delegated_role(rolename)
            for keyid in role.keyids:
                key = delegator.get_key(keyid)
                if key.unrecognized_fields["x-playground-keyowner"] in config.signers:
                    # signer is still a signer
                    config.signers.remove(key.unrecognized_fields["x-playground-keyowner"])
                else:
                    # signer was removed
                    delegator.revoke_key(keyid, rolename)

            # Add user themselves
            if self.user_name in config.signers:
                signing_key.unrecognized_fields["x-playground-keyowner"] = self.user_name
                delegator.add_key(signing_key, rolename)

            role.threshold = config.threshold

        # Modify the role itself
        # TODO only save new version if values change
        with self.edit(rolename) as signed:
            signed.unrecognized_fields["x-playground-expiry-period"] = config.expiry_period
            signed.unrecognized_fields["x-playground-signing-period"] = config.signing_period

        # Handle removed invitations
        for invited_signer, invited_roles in self._state_config["invites"].items():
            if invited_signer not in config.signers:
                if rolename in invited_roles:
                    invited_roles.remove(rolename)
                # TODO remve empty invited_roles lists?

        # Handle new invitations
        for signer in config.signers:
            if signer not in self._state_config["invites"]:
                self._state_config["invites"][signer] = []
            if rolename not in self._state_config["invites"][signer]:
                self._state_config["invites"][signer].append(rolename)

        with open(os.path.join(self._dir, ".signing-event-state"), "w") as f:
            f.write(json.dumps(self._state_config, indent=2))

    def status(self, rolename: str) -> str:
        return "TODO: Describe the changes in the signing event for this role"

    def sign(self, rolename: str):
        """Sign without payload changes"""
        md = self.open(rolename)
        for key in self._get_keys(rolename):
            keyowner = key.unrecognized_fields["x-playground-keyowner"]
            if keyowner == self.user_name:
                self._sign(rolename, md, key)
                self._write(rolename, md)
                return

        assert(f"{rolename} signing key for {self.user_name} not found")