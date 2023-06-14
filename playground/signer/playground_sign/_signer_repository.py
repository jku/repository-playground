# Copyright 2023 Google LLC

"""Internal repository module for playground signer tool"""

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, unique
import filecmp
from glob import glob
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Callable
from securesystemslib.exceptions import UnverifiedSignatureError
from securesystemslib.signer import Signature, Signer, SigstoreKey, SigstoreSigner, KEY_FOR_TYPE_AND_SCHEME, SIGNER_FOR_URI_SCHEME

from tuf.api.exceptions import UnsignedMetadataError
from tuf.api.metadata import DelegatedRole, Delegations, Key, Metadata, Root, TargetFile, Targets
from tuf.api.serialization.json import CanonicalJSONSerializer, JSONSerializer
from tuf.repository import Repository, AbortEdit


logger = logging.getLogger(__name__)

KEY_FOR_TYPE_AND_SCHEME[("sigstore-oidc", "Fulcio")] = SigstoreKey
SIGNER_FOR_URI_SCHEME[SigstoreSigner.SCHEME] = SigstoreSigner

@unique
class SignerState(Enum):
    NO_ACTION = 0,
    UNINITIALIZED = 1,
    INVITED = 2,
    SIGNATURE_NEEDED = 4,


@dataclass
class OnlineConfig:
    # All keys are used as signing keys for both snapshot and timestamp
    keys: list[Key]
    timestamp_expiry: int
    timestamp_signing: int
    snapshot_expiry: int
    snapshot_signing: int


@dataclass
class OfflineConfig:
    signers: list[str]
    threshold: int
    expiry_period: int
    signing_period: int


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


class SignerRepository(Repository):
    """A repository implementation for the signer tool"""

    def __init__(self, dir: str, prev_dir: str, user_name: str, secret_func: Callable[[str, str], str]):
        self.user_name = user_name
        self._dir = dir
        self._prev_dir = prev_dir
        self._get_secret = secret_func
        self._invites: dict[str, list[str]] = {}
        self._signers: dict[str, Signer] = {}

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

    def _known_good_version(self, rolename: str) -> int:
        prev_path = os.path.join(self._prev_dir, f"{rolename}.json")
        if os.path.exists(prev_path):
            with open(prev_path, "rb") as f:
                md = Metadata.from_bytes(f.read())
            return md.signed.version

        return 0

    def _known_good_root(self) -> Root:
        """Return the Root object from the known-good repository state"""
        prev_path = os.path.join(self._prev_dir, f"root.json")
        if os.path.exists(prev_path):
            with open(prev_path, "rb") as f:
                md = Metadata.from_bytes(f.read())
            assert isinstance(md.signed, Root)
            return md.signed
        else:
            # this role did not exist: return an empty one for comparison purposes
            return Root()

    def _known_good_targets(self, rolename: str) -> Targets:
        """Return a Targets object from the known-good repository state"""
        prev_path = os.path.join(self._prev_dir, f"{rolename}.json")
        if os.path.exists(prev_path):
            with open(prev_path, "rb") as f:
                md = Metadata.from_bytes(f.read())
            assert isinstance(md.signed, Targets)
            return md.signed
        else:
            # this role did not exist: return an empty one for comparison purposes
            return Targets()

    def _get_keys(self, role: str, known_good:bool = False) -> list[Key]:
        """Return public keys for delegated role

        If known_good is True, use the keys defined in known good delegator.
        Otherwise use keys defined in the signing event delegator.
        """
        if role in ["root", "timestamp", "snapshot", "targets"]:
            if known_good:
                delegator: Root | Targets = self._known_good_root()
            else:
                delegator = self.root()
        else:
            if known_good:
                delegator = self._known_good_targets("targets")
            else:
                delegator = self.targets()
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

        if key.keyid not in self._signers:
            # TODO Get key uri from .playground-sign.ini, avoid if-else here
            if key.keytype == "sigstore-oidc":
                self._signers[key.keyid] = Signer.from_priv_key_uri("sigstore:?ambient=false", key, secret_handler)
            else:
                self._signers[key.keyid] = Signer.from_priv_key_uri("hsm:", key, secret_handler)

        signer = self._signers[key.keyid]

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
                md: Metadata = Metadata(Root())
            else:
                md = Metadata(Targets())
            md.signed.unrecognized_fields["x-playground-expiry-period"] = 0
            md.signed.unrecognized_fields["x-playground-signing-period"] = 0
        else:
            with open(fname, "rb") as f:
                md = Metadata.from_bytes(f.read())

        return md

    def close(self, role: str, md: Metadata) -> None:
        """Write metadata to a file in the repository directory
        
        Note that resulting metadata is not signed and all existing
        signatures are removed.
        """
        # Make sure version is bumped only once per signing event
        md.signed.version = self._known_good_version(role) + 1

        # Set expiry based on custom metadata
        days = md.signed.unrecognized_fields["x-playground-expiry-period"]
        md.signed.expires = datetime.utcnow() + timedelta(days=days)

        # figure out if there are open invites to delegations of this role
        open_invites = False
        delegated = self._get_delegated_rolenames(md)
        for invited_roles in self._invites.values():
            for invited_role in invited_roles:
                if invited_role in delegated:
                    open_invites = True
                    break

        if role == "root":
            # special case: root includes its own signing keys. We want
            # to handle both old root keys (from known good version) and
            # new keys from the root version we are storing
            keys = self._get_keys(role, True)

            assert isinstance(md.signed, Root)
            r = md.signed.get_delegated_role("root")
            for keyid in r.keyids:
                duplicate = False
                for key in keys:
                    if keyid == key.keyid:
                        duplicate = True
                if not duplicate:
                    keys.append(md.signed.get_key(keyid))
        else:
            # for all other roles we can use the keys defined in
            # signing event
            keys = self._get_keys(role)

        # wipe signatures
        md.signatures.clear()
        for key in keys:
            md.signatures[key.keyid] = Signature(key.keyid, "")

            # Mark role as unsigned if user is a signer
            keyowner = key.unrecognized_fields["x-playground-keyowner"]
            if keyowner == self.user_name:
                if role not in self.unsigned:
                    self.unsigned.append(role)

        self._write(role, md)

    @staticmethod
    def _get_delegated_rolenames(md: Metadata) -> list[str]:
        if isinstance(md.signed, Root):
            return list(md.signed.roles.keys())
        elif isinstance(md.signed, Targets):
            if md.signed.delegations and md.signed.delegations.roles:
                return list(md.signed.delegations.roles.keys())
        return []

    def get_online_config(self) -> OnlineConfig:
        """Read configuration for online delegation from metadata"""
        root = self.root()

        timestamp_role = root.get_delegated_role("timestamp")
        snapshot_role = root.get_delegated_role("snapshot")
        timestamp_expiry = timestamp_role.unrecognized_fields["x-playground-expiry-period"]
        timestamp_signing = timestamp_role.unrecognized_fields.get("x-playground-signing-period")
        snapshot_expiry = snapshot_role.unrecognized_fields["x-playground-expiry-period"]
        snapshot_signing = snapshot_role.unrecognized_fields.get("x-playground-signing-period")

        if timestamp_signing is None:
            timestamp_signing = timestamp_expiry // 2
        if snapshot_signing is None:
            snapshot_signing = snapshot_expiry // 2
        keys = []
        for keyid in timestamp_role.keyids:
            keys.append(root.get_key(keyid))

        return OnlineConfig(keys, timestamp_expiry, timestamp_signing, snapshot_expiry, snapshot_signing)

    def set_online_config(self, online_config: OnlineConfig):
        """Store online delegation configuration in metadata."""

        with self.edit_root() as root:
            timestamp = root.get_delegated_role("timestamp")
            snapshot = root.get_delegated_role("snapshot")

            # Remove current keys
            for keyid in timestamp.keyids.copy():
                root.revoke_key(keyid, "timestamp")
            for keyid in snapshot.keyids.copy():
                root.revoke_key(keyid, "snapshot")

            # Add new keys
            for key in online_config.keys:
                root.add_key(key, "timestamp")
                root.add_key(key, "snapshot")

            # set online role periods
            timestamp.unrecognized_fields["x-playground-expiry-period"] = online_config.timestamp_expiry
            timestamp.unrecognized_fields["x-playground-signing-period"] = online_config.timestamp_signing
            snapshot.unrecognized_fields["x-playground-expiry-period"] = online_config.snapshot_expiry
            snapshot.unrecognized_fields["x-playground-signing-period"] = online_config.snapshot_signing

    def get_role_config(self, rolename: str) -> OfflineConfig | None:
        """Read configuration for delegation and role from metadata"""
        if rolename in ["timestamp", "snapshot"]:
            raise ValueError("online roles not supported")

        if rolename == "root":
            delegator: Root|Targets = self.root()
            delegated: Root|Targets = delegator
        elif rolename == "targets":
            delegator = self.root()
            delegated = self.targets()
        else:
            delegator = self.targets()
            delegated = self.targets(rolename)

        try:
            role = delegator.get_delegated_role(rolename)
        except ValueError:
            return None

        expiry = delegated.unrecognized_fields["x-playground-expiry-period"]
        signing = delegated.unrecognized_fields["x-playground-signing-period"]
        threshold = role.threshold
        signers = []
        # Include current invitees on config
        for signer, rolenames in self._invites.items():
            if rolename in rolenames:
                signers.append(signer)
        # Include current signers on config
        for keyid in role.keyids:
            try:
                key = delegator.get_key(keyid)
                signers.append(key.unrecognized_fields["x-playground-keyowner"])
            except ValueError:
                pass

        return OfflineConfig(signers, threshold, expiry, signing)

    def set_role_config(self, rolename: str, config: OfflineConfig, signing_key: Key | None):
        """Store delegation & role configuration in metadata.

        signing_key is only used if user is configured as signer"""
        if rolename in ["timestamp", "snapshot"]:
            raise ValueError("online roles not supported")

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
            # Find signers key
            is_signer = False
            for key in self._get_keys(rolename):
                if signer == key.unrecognized_fields["x-playground-keyowner"]:
                    is_signer = True

            # If signer does not have key, add invitation
            if not is_signer:
                if signer not in self._invites:
                    self._invites[signer] = []
                if rolename not in self._invites[signer]:
                    self._invites[signer].append(rolename)

        if rolename in ["root", "targets"]:
            delegator_cm = self.edit_root()
        else:
            delegator_cm = self.edit_targets()

        with delegator_cm as delegator:
            changed = False
            try:
                role = delegator.get_delegated_role(rolename)
            except ValueError:
                # Role does not exist yet: create delegation
                assert isinstance(delegator, Targets)
                role = DelegatedRole(rolename, [], 1, True, [f"{rolename}/*"])
                if not delegator.delegations:
                    delegator.delegations = Delegations({}, {})
                delegator.delegations.roles[rolename] = role
                changed = True

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
            invited = self.user_name in self._invites and rolename in self._invites[self.user_name]
            if invited and signing_key:
                signing_key.unrecognized_fields["x-playground-keyowner"] = self.user_name
                delegator.add_key(signing_key, rolename)

                self._invites[self.user_name].remove(rolename)
                if not self._invites[self.user_name]:
                    del self._invites[self.user_name]

                # Add role to unsigned list even if the role itself does not change
                if rolename not in self.unsigned:
                    self.unsigned.append(rolename)

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

        state_file_path = os.path.join(self._dir, ".signing-event-state")
        if self._invites:
            with open(state_file_path, "w") as f:
                state_file = {"invites": self._invites}
                f.write(json.dumps(state_file, indent=2))
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
