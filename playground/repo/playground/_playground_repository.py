from dataclasses import dataclass
from datetime import datetime, timedelta
from glob import glob
import json
import logging
import os
import shutil
from securesystemslib.exceptions import UnverifiedSignatureError
from securesystemslib.signer import Signature, Signer, SigstoreKey, SigstoreSigner, KEY_FOR_TYPE_AND_SCHEME
from sigstore.oidc import detect_credential

from tuf.api.metadata import Key, Metadata, MetaFile, Root, Snapshot, Targets, Timestamp
from tuf.repository import AbortEdit, Repository
from tuf.api.serialization.json import CanonicalJSONSerializer, JSONSerializer

# sigstore is not a supported key by default
KEY_FOR_TYPE_AND_SCHEME[("sigstore-oidc", "Fulcio")] = SigstoreKey

# TODO Add a metadata cache so we don't constantly open files
# TODO; Signing status probably should include an error message when valid=False

logger = logging.getLogger(__name__)

@dataclass
class SigningStatus:
    invites: set[str] # invites to _delegations_ of the role
    signed: set[str]
    missing: set[str]
    threshold: int
    valid: bool
    message: str | None

class SigningEventState:
    """Class to manage the .signing-event-state file"""
    def __init__(self, file_path: str):
        self._file_path = file_path
        self._invites = {}
        if os.path.exists(file_path):
            with open(file_path) as f:
                data = json.load(f)
                self._invites = data["invites"]

    def invited_signers_for_role(self, rolename: str) -> list[str]:
        signers = []
        for invited_signer, invited_rolenames in self._invites.items():
            if rolename in invited_rolenames:
                signers.append(invited_signer)
        return signers


class PlaygroundRepository(Repository):
    """A online repository implementation for use in GitHub Actions

    Arguments:
        dir: metadata directory to operate on
        prev_dir: optional known good repository directory
    """
    def __init__(self, dir: str, prev_dir: str|None = None):
        self._dir = dir
        self._prev_dir = prev_dir

        # read signing event state file
        self._state = SigningEventState(os.path.join(self._dir, ".signing-event-state"))

    def _get_filename(self, role: str) -> str:
        return f"{self._dir}/{role}.json"

    def _get_keys(self, role: str) -> list[Key]:
        """Return public keys for delegated role"""
        if role in ["root", "timestamp", "snapshot", "targets"]:
            delegator: Root|Targets = self.root()
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

    def open(self, role:str) -> Metadata:
        """Return existing metadata, or create new metadata

        This is an implementation of Repository.open()
        """
        fname = self._get_filename(role)

        if not os.path.exists(fname):
            if role not in ["timestamp", "snapshot"]:
                raise ValueError(f"Cannot create new {role} metadata")
            if role == "timestamp":
                md: Metadata = Metadata(Timestamp())
                # workaround https://github.com/theupdateframework/python-tuf/issues/2307
                md.signed.snapshot_meta.version = 0
            else:
                md = Metadata(Snapshot())
                # workaround https://github.com/theupdateframework/python-tuf/issues/2307
                md.signed.meta.clear()
            # this makes version bumping in close() simpler
            md.signed.version = 0
        else:
            with open(fname, "rb") as f:
                md = Metadata.from_bytes(f.read())

        return md


    def signing_expiry_period(self, rolename: str) -> tuple[int, int]:
        """Extracts the signing and expiry period for a role

        If no signing expiry is configured, half the expiry period is used.
        """
        if rolename in ["timestamp", "snapshot"]:
            role = self.root().get_delegated_role(rolename)
            expiry_days = role.unrecognized_fields["x-playground-expiry-period"]
            signing_days = role.unrecognized_fields.get("x-playground-signing-period")
        else:
            signed = self.root() if rolename == "root" else self.targets(rolename)
            expiry_days = signed.unrecognized_fields["x-playground-expiry-period"]
            signing_days = signed.unrecognized_fields.get("x-playground-signing-period")

        if signing_days is None:
            signing_days = expiry_days // 2

        return (signing_days, expiry_days)


    def close(self, rolename: str, md: Metadata) -> None:
        """Write metadata to a file in repo dir

        Implementation of Repository.close(). Signs online roles.
        """
        md.signed.version += 1

        _, expiry_days = self.signing_expiry_period(rolename)

        md.signed.expires = datetime.utcnow() + timedelta(days=expiry_days)

        md.signatures.clear()
        for key in self._get_keys(rolename):
            if rolename in ["timestamp", "snapshot"]:
                uri = key.unrecognized_fields["x-playground-online-uri"]
                # WORKAROUND while sigstoresigner is not finished
                if uri == "sigstore:":
                    signer = SigstoreSigner(detect_credential(), key)
                else:
                    signer = Signer.from_priv_key_uri(uri, key)
                md.sign(signer, True)
            else:
                # offline signer, add empty sig
                md.signatures[key.keyid] = Signature(key.keyid, "")

        if rolename in ["timestamp", "snapshot"]:
            root_md:Metadata[Root] = self.open("root")
            # repository should never write unsigned online roles
            root_md.verify_delegate(rolename, md)

        filename = self._get_filename(rolename)
        data = md.to_bytes(JSONSerializer())
        with open(filename, "wb") as f:
            f.write(data)


    @property
    def targets_infos(self) -> dict[str, MetaFile]:
        """Implementation of Repository.target_infos

        Called by snapshot() when it needs current targets versions
        """
        # Note that this ends up loading every targets metadata. This could be
        # avoided if this data was produced in the signing event (as then we
        # know which targets metadata changed). Snapshot itself should not be
        # done before the signing event PR is reviewed though as the online keys
        # are then exposed
        targets_files: dict[str, MetaFile] = {}

        targets = self.targets()
        targets_files["targets.json"] = MetaFile(targets.version)
        if targets.delegations and targets.delegations.roles:
            for role in targets.delegations.roles.values():
                version = self.targets(role.name).version
                targets_files[f"{role.name}.json"] = MetaFile(version)

        return targets_files

    @property
    def snapshot_info(self) -> MetaFile:
        """Implementation of Repository.snapshot_info

        Called by timestamp() when it needs current snapshot version
        """
        return MetaFile(self.snapshot().version)

    def open_prev(self, role:str) -> Metadata | None:
        """Return known good metadata for role (if it exists)"""
        prev_fname = f"{self._prev_dir}/{role}.json"
        if os.path.exists(prev_fname):
            with open(prev_fname, "rb") as f:
                return Metadata.from_bytes(f.read())

        return None

    def _validate_role(self, delegator: Metadata, rolename: str) -> tuple[bool, str | None]:
        """Validate role compatibility with this repository

        Returns bool for validity and optional error message"""
        md = self.open(rolename)
        prev_md = self.open_prev(rolename)

        # Current checks are more examples than actual checks: this should be much more strict

        if prev_md and md.signed.version <= prev_md.signed.version:
            return False, f"Version {md.signed.version} is not valid for {rolename}"

        days = md.signed.unrecognized_fields["x-playground-expiry-period"]
        if md.signed.expires > datetime.utcnow() + timedelta(days=days):
            return False, f"Expiry date is further than expected {days} days ahead"

        # TODO for root:
        # * check version is prev_version + 1
        # * check delegations are correct, consistent_snapshot is on

        # TODO for top-level targets:
        # * check delegations are expected
        # * check that target files in metadata match the files in targets/

        # TODO for delegated targets:
        # * check there are no delegations
        # * check that target files in metadata match the files in targets/

        try:
            delegator.verify_delegate(rolename, md)
        except:
            return False, None

        return True, None

    def _get_signing_status(self, delegator: Metadata, rolename: str) -> SigningStatus:
        """Build signing status for role.

        This method relies on event state (.signing-event-state) to be accurate.
        """
        invites = set()
        sigs = set()
        missing_sigs = set()
        md = self.open(rolename)

        # Build list of invites to all delegated roles of rolename
        delegation_names = []
        if rolename == "root":
            delegation_names = ["root", "targets"]
        elif rolename == "targets":
            if md.signed.delegations:
                delegation_names = md.signed.delegations.roles.keys()
        for delegation_name in delegation_names:
            invites.update(self._state.invited_signers_for_role(delegation_name))

        role = delegator.signed.get_delegated_role(rolename)

        # Build lists of signed signers and not signed signers
        for key in self._get_keys(rolename):
            keyowner = key.unrecognized_fields["x-playground-keyowner"]
            try:
                payload = CanonicalJSONSerializer().serialize(md.signed)
                key.verify_signature(md.signatures[key.keyid], payload)
                sigs.add(keyowner)
            except (KeyError, UnverifiedSignatureError):
                missing_sigs.add(keyowner)

        # Just to be sure: double check that delegation threshold is reached
        valid, msg = self._validate_role(delegator, rolename)

        return SigningStatus(invites, sigs, missing_sigs, role.threshold, valid, msg)

    def status(self, rolename: str) -> tuple[SigningStatus, SigningStatus | None]:
        """Returns signing status for role.

        In case of root, another SigningStatus is returned for the previous root.
        Uses .signing-event-state file."""
        if rolename in ["timestamp", "snapshot"]:
            raise ValueError(f"Not supported for online metadata")

        prev_md = self.open_prev(rolename)
        prev_status = None

        # Find out the signing status of the role
        if rolename == "root":
            # new root must be signed so it satisfies both old and new root
            if prev_md:
                prev_status = self._get_signing_status(prev_md, rolename)
            delegator = self.open("root")
        elif rolename == "targets":
            delegator = self.open("root")
        else:
            delegator = self.open("targets")

        return self._get_signing_status(delegator, rolename), prev_status

    def publish(self, directory: str):
        metadata_dir = os.path.join(directory, "metadata")
        targets_dir = os.path.join(directory, "targets")
        os.makedirs(metadata_dir, exist_ok=True)

        for src_path in glob(os.path.join(self._dir, "root_history", "*.root.json")):
            shutil.copy(src_path, metadata_dir)
        shutil.copy(os.path.join(self._dir, "timestamp.json"), metadata_dir)

        snapshot = self.snapshot()
        dst_path = os.path.join(metadata_dir, f"{snapshot.version}.snapshot.json")
        shutil.copy(os.path.join(self._dir, "snapshot.json"), dst_path)

        for filename, metafile  in snapshot.meta.items():
            src_path = os.path.join(self._dir, filename)
            dst_path = os.path.join(metadata_dir, f"{metafile.version}.{filename}")
            shutil.copy(src_path, dst_path)

            targets = self.targets(filename[:-len(".json")])
            for target in targets.targets.values():
                parent, sep, name = target.path.rpartition("/")
                os.makedirs(os.path.join(targets_dir, parent), exist_ok=True)
                src_path = os.path.join(self._dir, "..", "targets", parent, name)
                for hash in target.hashes.values():
                    dst_path = os.path.join(targets_dir, parent, f"{hash}.{name}")
                    shutil.copy(src_path, dst_path)


    def bump_expiring(self, rolename:str) -> int | None:
        """Create a new version of role if it is about to expire"""
        now = datetime.utcnow()
        bumped = True

        with self.edit(rolename) as signed:
            signing_days, _ = self.signing_expiry_period(rolename)
            delta = timedelta(days=signing_days)

            logger.debug(f"{rolename} signing period starts {signed.expires - delta}")
            if now + delta < signed.expires:
                # no need to bump version
                bumped = False
                raise AbortEdit

        return signed.version if bumped else None
