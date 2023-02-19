from dataclasses import dataclass
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from securesystemslib.signer import Signer
from securesystemslib.exceptions import UnverifiedSignatureError

from tuf.api.metadata import Key, Metadata, MetaFile, Snapshot, Targets, Timestamp
from tuf.api.serialization.json import JSONSerializer
from tuf.repository import Repository
from tuf.api.serialization.json import CanonicalJSONSerializer

# TODO Add a metadata cache so we don't constantly open files


# TODO; Signing status probably should include an error message when valid=False
@dataclass
class SigningStatus:
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

    def _get_filename(self, role: str) -> str:
        return f"{self._dir}/{role}.json"

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
    def targets_infos(self) -> Dict[str, MetaFile]:
        """Implementation of Repository.target_infos"""
        raise NotImplementedError

    @property
    def snapshot_info(self) -> MetaFile:
        """Implementation of Repository.snapshot_info"""
        raise NotImplementedError

    def open_prev(self, role:str) -> Optional[Metadata]:
        """Return known good metadata for role (if it exists)"""
        prev_fname = f"{self._prev_dir}/{role}.json"
        if os.path.exists(prev_fname):
            with open(prev_fname, "rb") as f:
                return Metadata.from_bytes(f.read())

        return None

    def _get_signing_status(self, delegator: Metadata, rolename: str) -> SigningStatus:
        sigs = set()
        missing_sigs = set()

        # Build lists of signed signers and not signed signers
        delegate = self.open(rolename)
        prev_delegate = self.open_prev(rolename)
        payload = CanonicalJSONSerializer().serialize(delegate.signed)
        role = delegator.signed.get_delegated_role(rolename)
        for keyid in role.keyids:
            try:
                key: Key = delegator.signed.get_key(keyid)
            except ValueError:
                continue

            try:
                key.verify_signature(delegate.signatures[keyid], payload)
                sigs.add(key.unrecognized_fields["x-playground-keyowner"])
            except (KeyError, UnverifiedSignatureError):
                missing_sigs.add(key.unrecognized_fields["x-playground-keyowner"])

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

        return SigningStatus(sigs, missing_sigs, role.threshold, valid)

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
