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

    def write(self):
        with open(self._file_path, "w") as f:
            data = {"invites": self._invites}
            f.write(json.dumps(data, indent=2))


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
        self._state = SigningEventState(os.path.join(self._dir, ".signing-event-state"))

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
        """Build signing status for role.

        This method relies on event state (.signing-event-state) to be accurate.
        """
        invites = set()
        sigs = set()
        missing_sigs = set()
        md = self.open(rolename)

        # Build list of invites to all delegated roles of rolename
        if rolename == "root":
            delegation_names = md.signed.roles.keys()
        elif rolename == "targets":
            delegation_names = []
            if md.signed.delegations:
                delegation_names = md.signed.delegations.roles.keys()
        for delegation_name in delegation_names:
            invites.update(self._state.invited_signers_for_role(delegation_name))

        prev_md = self.open_prev(rolename)
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
        valid = True
        try:
            delegator.verify_delegate(rolename,md)
        except:
            valid = False

        # Other checks to ensure repository continuity        
        if prev_md and md.signed.version <= prev_md.signed.version:
            valid = False

        # TODO more checks here

        return SigningStatus(invites, sigs, missing_sigs, role.threshold, valid)

    def status(self, rolename: str) -> tuple[SigningStatus, SigningStatus | None]:
        """Returns signing status for role.

        In case of root, another SigningStatus is rturned for the previous root.
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
