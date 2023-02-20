from dataclasses import dataclass
import json
import os
from securesystemslib.exceptions import UnverifiedSignatureError

from tuf.api.metadata import Key, Metadata, MetaFile, Root, Snapshot, Targets, Timestamp
from tuf.repository import Repository
from tuf.api.serialization.json import CanonicalJSONSerializer

# TODO Add a metadata cache so we don't constantly open files


# TODO; Signing status probably should include an error message when valid=False
@dataclass
class SigningStatus:
    invites: set[str] # invites to _delegations_ of the role
    signed: set[str]
    missing: set[str]
    threshold: int
    valid: bool


class PlaygroundRepository(Repository):
    """A online repository implementation for use in GitHub Actions
    
    Arguments:
        dir: metadata directory to operate on
        prev_dir: optional known good repository directory
    """
    def __init__(self, dir: str, prev_dir: str = None):
        self._dir = dir
        self._prev_dir = prev_dir

        # read signing event state file
        self._state_config = {"invites": {}, "unsigned": {}}
        state_file = os.path.join(self._dir, ".signing-event-state")
        if os.path.exists(state_file):
            with open(state_file) as f:
                self._state_config  = json.load(f)

    def _get_filename(self, role: str) -> str:
        return f"{self._dir}/{role}.json"

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

    def open(self, role:str) -> Metadata:
        """Return existing metadata, or create new metadata
        
        This is an implementation of Repository.open()
        """
        fname = self._get_filename(role)

        if not os.path.exists(fname):
            if role not in ["timestamp", "snapshot"]:
                raise ValueError(f"Cannot create new {role} metadata")
            if role == "timestamp":
                md = Metadata(Timestamp())
            else:
                md = Metadata(Snapshot())
            # this makes version bumping in close() simpler
            md.signed.version = 0
        else:
            with open(fname, "rb") as f:
                md = Metadata.from_bytes(f.read())

        return md

    def close(self, role: str, md: Metadata) -> None:
        """Write metadata to a file in repo dir
        
        Implementation of Repository.close()
        """
        if role not in ["timestamp", "snapshot"]:
            raise ValueError(f"Cannot store new {role} metadata")

        # TODO sign and write file
        raise NotImplementedError

    @property
    def targets_infos(self) -> dict[str, MetaFile]:
        """Implementation of Repository.target_infos"""
        raise NotImplementedError

    @property
    def snapshot_info(self) -> MetaFile:
        """Implementation of Repository.snapshot_info"""
        raise NotImplementedError

    def open_prev(self, role:str) -> Metadata | None:
        """Return known good metadata for role (if it exists)"""
        prev_fname = f"{self._prev_dir}/{role}.json"
        if os.path.exists(prev_fname):
            with open(prev_fname, "rb") as f:
                return Metadata.from_bytes(f.read())

        return None

    def _get_signing_status(self, delegator: Metadata, rolename: str) -> SigningStatus:
        invites = set()
        sigs = set()
        missing_sigs = set()
        delegate = self.open(rolename)

        # Build list of invites for all delegated roles of the delegate
        for keyowner, rolenames in self._state_config["invites"].items():
            if rolename == "root":
                if set(rolenames).intersection(delegate.signed.roles):
                    invites.add(keyowner)
            elif rolename == "targets":
                if delegate.signed.delegations and set(rolenames).intersection(delegate.signed.delegations.roles):
                    invites.add(keyowner)

        # Build lists of signed signers and not signed signers
        # This relies on "unsigned" state configuration being up-to-date
        prev_delegate = self.open_prev(rolename)
        role = delegator.signed.get_delegated_role(rolename)

        for keyowner, rolenames in self._state_config["unsigned"].items():
            if rolename in rolenames:
                missing_sigs.add(keyowner)

        for key in self._get_keys(rolename):
            keyowner = key.unrecognized_fields["x-playground-keyowner"]
            if keyowner not in missing_sigs:
                sigs.add(keyowner)

        # Just to be sure: double check that delegation threshold is reached
        valid = True
        try:
            delegator.verify_delegate(rolename,delegate)
        except:
            valid = False

        # Other checks to ensure repository continuity        
        if prev_delegate and delegate.signed.version <= prev_delegate.signed.version:
            valid = False

        # TODO more checks here

        return SigningStatus(invites, sigs, missing_sigs, role.threshold, valid)

    def status(self, rolename: str) -> tuple[SigningStatus, SigningStatus | None]:
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

    def request_signatures(self, rolename: str):
        md = self.open(rolename)
        payload = CanonicalJSONSerializer().serialize(md.signed)
        updated = False
        for key in self._get_keys(rolename):
            keyowner = key.unrecognized_fields["x-playground-keyowner"]
            try:
                key.verify_signature(md.signatures[key.keyid], payload)
                if keyowner in self._state_config["unsigned"] and rolename in self._state_config["unsigned"][keyowner]:
                    self._state_config["unsigned"][keyowner].remove(rolename)
                    if not self._state_config["unsigned"][keyowner]:
                        del self._state_config["unsigned"][keyowner]
                    updated = True

            except (KeyError, UnverifiedSignatureError):
                if keyowner not in self._state_config["unsigned"]:
                    self._state_config["unsigned"][keyowner] = []
                if rolename not in self._state_config["unsigned"][keyowner]:
                    self._state_config["unsigned"][keyowner].append(rolename)
                    updated = True

        if updated:
            with open(os.path.join(self._dir, ".signing-event-state"), "w") as f:
                f.write(json.dumps(self._state_config, indent=2))
