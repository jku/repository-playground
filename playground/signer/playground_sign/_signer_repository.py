# Copyright 2023 Google LLC

"""Internal repository module for playground signer tool"""

from dataclasses import dataclass
from enum import Enum, unique
import filecmp
from glob import glob
import json
import os
from datetime import datetime, timedelta
from typing import Callable, Optional
from securesystemslib.exceptions import UnverifiedSignatureError
from securesystemslib.signer import Signature, Signer

from tuf.api.exceptions import UnsignedMetadataError
from tuf.api.metadata import Key, Metadata, MetaFile, Root, Targets
from tuf.api.serialization.json import CanonicalJSONSerializer, JSONSerializer
from tuf.repository import Repository, AbortEdit

def _find_changed_roles(known_good_dir: str, signing_event_dir: str) -> list[str]:
    """Return list of roles that exist and have changed in this signing event"""
    files = glob("*.json", root_dir=signing_event_dir)
    changed_roles = []
    for fname in files:
        if (
            not os.path.exists(f"{known_good_dir}/{fname}") or
            not filecmp.cmp(f"{signing_event_dir}/{fname}", f"{known_good_dir}/{fname}",  shallow=False)
        ):
            if fname in ["timestamp.json", "snapshot.json"]:
                assert("Unexpected change in online files")

            changed_roles.append(fname[:-len(".json")])

    # reorder, toplevels first
    for toplevel in ["targets", "root"]:
        if toplevel in changed_roles:
            changed_roles.remove(toplevel)
            changed_roles.insert(0, toplevel)

    return changed_roles

@unique
class SignerState(Enum):
    NO_ACTION = 0,
    UNINITIALIZED = 1,
    INVITED = 2,
    SIGNATURE_NEEDED = 3,


@dataclass
class OnlineConfig:
    key: Optional[Key]
    uri: Optional[str]
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

    def __init__(self, dir: str, prev_dir: str, user_name: str, secret_func: Callable[[str, str], str]):
        self.user_name = user_name
        self._dir = dir
        self._prev_dir = prev_dir
        self._get_secret = secret_func
        self._invites: dict[str, list[str]] = {}

        # read signing event state file (invites)
        state_file = os.path.join(self._dir, ".signing-event-state")
        if os.path.exists(state_file):
            with open(state_file) as f:
                config = json.load(f)
            self._invites = config["invites"]

        # Figure out needed signatures
        self.unsigned = []
        for rolename in _find_changed_roles(self._prev_dir, self._dir):
            if self._user_signature_needed(rolename) and rolename not in self.invites:
                self.unsigned.append(rolename)

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
        """Return the list of roles the user has been invited to"""
        try:
            return self._invites[self.user_name]
        except KeyError:
            return []

    def _user_signature_needed(self, rolename: str) -> bool:
        """Return true if current role metadata is unsigned by user"""
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

    def _prev_version(self, rolename: str) -> int:
        prev_path = os.path.join(self._prev_dir, f"{rolename}.json")
        if os.path.exists(prev_path):
            with open(prev_path, "rb") as f:
                md = Metadata.from_bytes(f.read())
            return md.signed.version

        return 0

    def _get_keys(self, role: str) -> list[Key]:
        """Return public keys for delegated role"""
        if role in ["root", "timestamp", "snapshot", "targets"]:
            delegator = self.open("root").signed
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
        while True:
            try:
                md.sign(signer, True)
                break
            except UnsignedMetadataError:
                print(f"Failed to sign {role} with {self.user_name} key. Try again?")


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
            md.signed.unrecognized_fields["x-playground-expiry-period"] = 0
            md.signed.unrecognized_fields["x-playground-signing-period"] = 0
        else:
            with open(fname, "rb") as f:
                md = Metadata.from_bytes(f.read())

        return md

    def close(self, role: str, md: Metadata) -> None:
        """Write metadata to a file in the repository directory"""
        # Make sure version is bumped only once per signing event
        md.signed.version = self._prev_version(role) + 1

        # Set expiry based on custom metadata
        days = md.signed.unrecognized_fields["x-playground-expiry-period"]
        md.signed.expires = datetime.utcnow() + timedelta(days=days)

        md.signatures.clear()
        for key in self._get_keys(role):
            keyowner = key.unrecognized_fields["x-playground-keyowner"]
            if keyowner == self.user_name:
                self._sign(role, md, key)
            else:
                # another offline signer: add empty signature
                md.signatures[key.keyid] = Signature(key.keyid, "")

        self._write(role, md)

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
            delegator = md
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
        for signer, rolenames in self._invites.items():
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

    def set_role_config(self, rolename: str, config: OfflineConfig, signing_key: Optional[Key]):
        """Store delegation & role configuration in metadata.

        signing_key is only used if user is configured as signer"""
        if rolename in ["timestamp", "snapshot"]:
            raise ValueError("online roles not supported")

        if rolename in ["root", "targets"]:
            delegator_name = "root"
        else:
            delegator_name = "targets"

        with self.edit(delegator_name) as delegator:
            # Handle existing signers
            changed = False
            role = delegator.get_delegated_role(rolename)
            for keyid in role.keyids:
                key = delegator.get_key(keyid)
                if key.unrecognized_fields["x-playground-keyowner"] in config.signers:
                    # signer is still a signer
                    config.signers.remove(key.unrecognized_fields["x-playground-keyowner"])
                else:
                    # signer was removed
                    delegator.revoke_key(keyid, rolename)
                    changed = True

            # Add user themselves
            if self.user_name in config.signers and signing_key:
                signing_key.unrecognized_fields["x-playground-keyowner"] = self.user_name
                delegator.add_key(signing_key, rolename)
                config.signers.remove(self.user_name)
                changed = True

            if role.threshold != config.threshold:
                changed = True
            role.threshold = config.threshold

            if not changed:
                # Exit the edit-contextmanager without saving if no changes were done
                raise AbortEdit(f"No changes to delegator of {rolename}")

        # Modify the role itself
        with self.edit(rolename) as signed:
            expiry = signed.unrecognized_fields.get("x-playground-expiry-period")
            signing = signed.unrecognized_fields.get("x-playground-signing-period")
            if expiry == config.expiry_period and signing == config.signing_period:
                raise AbortEdit(f"No changes to {rolename}")

            signed.unrecognized_fields["x-playground-expiry-period"] = config.expiry_period
            signed.unrecognized_fields["x-playground-signing-period"] = config.signing_period

        # Remove invites for the role
        new_invites = {}
        for invited_signer, invited_roles in self._invites.items():
            if rolename in invited_roles:
                invited_roles.remove(rolename)
            if invited_roles:
                new_invites[invited_signer] = invited_roles
        self._invites = new_invites

        # Handle new invitations
        for signer in config.signers:
            if signer not in self._invites:
                self._invites[signer] = []
            if rolename not in self._invites[signer]:
                self._invites[signer].append(rolename)

        state_file_path = os.path.join(self._dir, ".signing-event-state")
        if self._invites:
            with open(state_file_path, "w") as f:
                config = {"invites": self._invites}
                f.write(json.dumps(config, indent=2))
        elif os.path.exists(state_file_path):
            os.remove(state_file_path)

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