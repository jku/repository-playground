import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from securesystemslib.signer import Signer
from securesystemslib.exceptions import UnverifiedSignatureError

from tuf.api.metadata import Key, Metadata, MetaFile, Snapshot, Targets, Timestamp
from tuf.repository import Repository
from tuf.api.serialization.json import CanonicalJSONSerializer


# TODO Add a metadata cache so we don't constantly open files

class OnlineRepo(Repository):
    """A online repository implementation for use in GitHub Actions
    
    Arguments:
        dir: repository directory to operate on
        prev_dir: optional known good repository directory
    """

    def __init__(self, dir: str, prev_dir: str = None):
        self._dir = dir
        self._prev_dir = prev_dir

        root_md = self.open("root")

        self._signers: Dict[str, Signer] = {}
        for rolename in ["timestamp", "snapshot"]:
            # https://github.com/theupdateframework/python-tuf/issues/2272
            role = root_md.signed.get_delegated_role(rolename)
            assert len(role.keyids) == 1
            key = root_md.signed.get_key(role.keyids[0])
            uri = key.unrecognized_fields["x-playground-online-uri"]
            self._signers[rolename] = Signer.from_priv_key_uri(uri, key)

    def _get_filename(self, role: str) -> str:
        # NOTE for now store non-versioned files in git. This is nice for
        # diffability but will likely need an exception for root...
        return f"{self._dir}/{role}.json"

    def _get_expiry(self, role: str) -> datetime:
        # TODO be smarter about expiry
        return datetime.utcnow() + timedelta(days=365)

    def open_prev(self, role:str) -> Optional[Metadata]:
        """Return known good metadata for role (if it exists)"""
        prev_fname = f"{self._prev_dir}/{role}.json"
        if os.path.exists(prev_fname):
            with open(prev_fname, "rb") as f:
                return Metadata.from_bytes(f.read())

        return None

    def open(self, role:str) -> Metadata:
        """Return metadata from repo dir, or create new metadata"""
        fname = self._get_filename(role)

        if not os.path.exists(fname):
            assert role in ["timestamp", "snapshot"]
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
        """Write metadata to a file in repo dir"""
        assert role in ["timestamp", "snapshot"]

        md.signed.version += 1
        md.signed.expires = self._get_expiry(role)
        
        md.sign(self._signers[role])

        with open(self._get_filename(role), "wb") as f:
            f.write(md.to_bytes())

    @property
    def targets_infos(self) -> Dict[str, MetaFile]:
        """Build list of targets metadata based on delegations and role versions"""
        # Reads all targets metadata from file, does not verify them
        targets_md: Metadata[Targets] = self.open("targets")

        infos = {"targets": MetaFile(targets_md.signed.version)}
        if targets_md.signed.delegations:
            for name in targets_md.signed.delegations.roles:
                role_md: Metadata[Targets] = self.open(name)
                infos[name] = MetaFile(role_md.signed.version)

        return infos

    @property
    def snapshot_info(self) -> MetaFile:
        snapshot_md: Metadata[Snapshot] = self.open("snapshot")
        return MetaFile(snapshot_md.signed.version)

    def verify(self, role: str):
        """Make sure submitted metadata is acceptable for inclusion in repository

        It is the callers responsibility to call this in the order that makes sense
        -- e.g. if both root and targets have changed, root should be verified first
        """
        # this is only for non-online metadata submissions
        assert role not in ["timestamp", "snapshot"]

        # load the previous and submitted versions of this metadata
        prev_md = self.open_prev(role)
        md = self.open(role)

        # load delegating metadata
        if role == "root":
            # The previous root must also verify new root
            if prev_md:
                prev_md.verify_delegate(role, md)
            delegator_md = md
        elif role == "targets":
            delegator_md = self.open("root")
        else:
            delegator_md = self.open("targets")

        if prev_md and md.signed.version <= prev_md.signed.version:
            raise ValueError(f"Unexpected version {md.signed.version}")

        # verify signatures
        delegator_md.verify_delegate(role, md)

        # TODO check that "expires" and other content in the metadata is acceptable to this repository


    def get_signature_state(self, rolename: str) -> Tuple[Set[str], Set[str], int]:
        """Return signed signers, missing signers, and threshold"""
        # this is only for non-online metadata submissions
        assert rolename not in ["timestamp", "snapshot"]

        md = self.open(rolename)
        data = CanonicalJSONSerializer().serialize(md.signed)

        # load delegating metadata
        delegators: List[Metadata] = []
        if rolename == "root":
            # new root must be signed so it satisfies both old and new root
            prev_md = self.open_prev("root")
            if prev_md:
                    delegators.append(prev_md)
            delegators.append(md)
        elif rolename == "targets":
            delegators.append(self.open("root"))
        else:
            delegators.append(self.open("targets"))

        # count signatures
        missing = set()
        signed = set()
        for delegator in delegators:
            role = delegator.signed.get_delegated_role(rolename)
            for keyid in role.keyids:
                try:
                    key: Key = delegator.signed.get_key(keyid)
                except ValueError:
                    continue

                try:
                    key.verify_signature(md.signatures[keyid], data)
                    signed.add(key.unrecognized_fields["x-playground-signer"])
                except (KeyError, UnverifiedSignatureError):
                    missing.add(key.unrecognized_fields["x-playground-signer"])

        return signed, missing, role.threshold