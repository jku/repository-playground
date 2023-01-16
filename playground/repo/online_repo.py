import os
from datetime import datetime, timedelta
from typing import Dict
from securesystemslib.signer import Signer

from tuf.api.metadata import Metadata, MetaFile, Snapshot, Targets, Timestamp
from tuf.repository import Repository

# TODO Add a metadata cache so we don't constantly open files

class OnlineRepo(Repository):
    """A online repository implementation for use in GitHub Actions """

    def __init__(self, dir: str):
        self._dir = dir

        root_md = self.open("root")

        self._signers: Dict[str, Signer] = {}
        for rolename in ["timestamp", "snapshot"]:
            # https://github.com/theupdateframework/python-tuf/issues/2272
            role, keys = root_md._get_role_and_keys(rolename)
            assert len(role.keyids) == 1
            key = keys[role.keyids[0]]
            uri = key.unrecognized_fields["x-playground-online-uri"]
            self._signers[rolename] = Signer.from_priv_key_uri(uri, key)

    def _get_filename(self, role: str) -> str:
        # NOTE for now store non-versioned files in git. This is nice for
        # diffability but will likely need an exception for root...
        return f"{self._dir}/{role}.json"

    def _get_expiry(self, role: str) -> datetime:
        # TODO be smarter about expiry
        return datetime.utcnow() + timedelta(days=365)

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
        """Build list of targets metadata based on delegations and filenames"""
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

    def verify(self, role: str, known_good_dir: str):
        """Make sure submitted metadata is acceptable for inclusion in repository

        It is the callers responsibility to call this in the order that makes sense
        -- e.g. if both root and targets have changed, root should be verified first
        """
        # this is only for non-online metadata submissions
        assert role not in ["timestamp", "snapshot"]

        # load the known good version of this metadata (if it exists)
        known_good_fname = f"{known_good_dir}/{role}.json"
        known_good_md = None
        known_good_version = 0
        if os.path.exists(known_good_fname):
            with open(known_good_fname, "rb") as f:
                known_good_md = Metadata.from_bytes(f.read())
            known_good_version = known_good_md.signed.version

        md = self.open(role)

        # load delegating metadata
        if role == "root":
            # The previous root must also verify new root
            if known_good_md:
                known_good_md.verify_delegate(role, md)
            delegator_md = md
        elif role == "targets":
            delegator_md = self.open("root")
        else:
            delegator_md = self.open("targets")

        # verify signatures
        delegator_md.verify_delegate(role, md)

        if md.signed.version <= known_good_version:
            raise ValueError(f"Unexpected version {md.signed.version}")

        # TODO check that "expires" and other content in the metadata is acceptable to this repository
