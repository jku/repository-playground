import subprocess
import click
import os
from datetime import datetime, timedelta
from typing import Dict, List
from securesystemslib.signer import Signature, Signer

from tuf.api.metadata import Key, Metadata, MetaFile, Root, Snapshot, Targets, Timestamp
from tuf.repository import Repository

def unmodified_in_git(filepath: str) -> bool:
    """Return True if the file is in git, and does not have changes in index"""
    cmd = ["git", "ls-files", "--error-unmatch", "--", filepath]
    if subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) != 0:
        return False

    cmd = ["git", "diff", "--exit-code", "--no-patch", "--", filepath]
    return subprocess.call(cmd) != 0

class ToolRepo(Repository):
    """A local repository implementation for the signer tool

    ToolRepo """

    def __init__(self, dir: str, user_name: str):
        self._dir = dir
        self._user_name = user_name

        os.makedirs(f"{self._dir}/root_history")

    def _get_filename(self, role: str) -> str:
        return f"{self._dir}/{role}.json"

    def _get_versioned_root_filename(self, version: int) -> str:
        return f"{self._dir}/root_history/{version}.root.json"

    def _get_expiry(self, role: str) -> datetime:
        # TODO be smarter about expiry
        return datetime.utcnow() + timedelta(days=365)

    def _get_keys(self, role: str, md: Metadata) -> List[Key]:
        """Lookup signing keys from delegating role"""
        
        if role == "root":
            pass # use the metadata we have already
        elif role in ["timestamp", "snapshot", "targets"]:
            md = self.open("root")
        else:
            md = self.open("targets")

        # https://github.com/theupdateframework/python-tuf/issues/2272
        r, keys = md._get_role_and_keys(role)
        return [key for key in keys.values() if key.keyid in r.keyids ]

    def _sign(self, md: Metadata, key: Key) -> None:
        def secret_handler(secret: str) -> str:
            return click.prompt(f"Enter {secret} to sign metadata", hide_input=True)

        if self._user_name != key.unrecognized_fields["x-playground-signer"]:
            # another signer: add empty signature
            md.signatures[key.keyid] = Signature(key.keyid, "")
        else:
            signer = Signer.from_priv_key_uri("hsm:", key, secret_handler)
            md.sign(signer, True)

    def open(self, role:str) -> Metadata:
        """Return metadata from repo dir, or create new metadata"""
        fname = self._get_filename(role)

        if not os.path.exists(fname):
            initializers = {
                Root.type: Root,
                Snapshot.type: Snapshot,
                Targets.type: Targets,
                Timestamp.type: Timestamp,
            }
            initializer = initializers.get(role, Targets)
            md = Metadata(initializer())

        else:
            with open(fname, "rb") as f:
                md = Metadata.from_bytes(f.read())

        return md

    def close(self, role: str, md: Metadata) -> None:
        """Write metadata to a file in repo dir"""
        filename = self._get_filename(role)

        # Avoid bumping version within a single commit
        if unmodified_in_git(filename):
            md.signed.version += 1

        md.signed.expires = self._get_expiry(role)

        md.signatures.clear()
        for key in self._get_keys(role, md):
            if self._user_name != key.unrecognized_fields["x-playground-signer"]:
                # another signer: add empty signature
                md.signatures[key.keyid] = Signature(key.keyid, "")
            else:
                self._sign(md, key)

        data = md.to_bytes()
        with open(filename, "wb") as f:
            f.write(data)
        if role == "root":
            with open(self._get_versioned_root_filename(md.signed.version), "wb") as f:
                f.write(data)

    @property
    def targets_infos(self) -> Dict[str, MetaFile]:
        raise NotImplementedError

    @property
    def snapshot_info(self) -> MetaFile:
        raise NotImplementedError
