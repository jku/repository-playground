import subprocess
import click
import os
from datetime import datetime, timedelta
from typing import Dict, List
from securesystemslib.signer import Signature, Signer

from tuf.api.metadata import Key, Metadata, MetaFile, Root, Signed, Snapshot, TargetFile, Targets, Timestamp
from tuf.api.serialization.json import JSONSerializer
from tuf.repository import AbortEdit, Repository

def unmodified_in_git(filepath: str) -> bool:
    """Return True if the file is in git, and does not have changes in index"""
    cmd = ["git", "ls-files", "--error-unmatch", "--", filepath]
    if subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) != 0:
        return False

    cmd = ["git", "diff", "--exit-code", "--no-patch", "--", filepath]
    return subprocess.call(cmd) == 0

class ToolRepo(Repository):
    """A local repository implementation for the signer tool

    ToolRepo """

    def __init__(self, dir: str, user_name: str):
        self._dir = dir
        self.user_name = user_name

        os.makedirs(f"{self._dir}/root_history",exist_ok=True)

    def _get_filename(self, role: str) -> str:
        return f"{self._dir}/{role}.json"

    def _get_versioned_root_filename(self, version: int) -> str:
        return f"{self._dir}/root_history/{version}.root.json"

    def _get_expiry(self, role: str) -> datetime:
        # TODO be smarter about expiry
        return datetime.utcnow() + timedelta(days=365)

    def _get_keys(self, role: str, signed: Signed) -> List[Key]:
        """Lookup signing keys from delegating role"""
        
        if role == "root":
            pass # use the Signed we have already
        elif role in ["timestamp", "snapshot", "targets"]:
            signed = self.open("root").signed
        else:
            signed = self.open("targets").signed

        # https://github.com/theupdateframework/python-tuf/issues/2272
        r = signed.get_delegated_role(role)
        keys = []
        for keyid in r.keyids:
            try:
                keys.append(signed.get_key(keyid))
            except ValueError:
                pass
        return keys

    def _sign(self, md: Metadata, key: Key) -> None:
        def secret_handler(secret: str) -> str:
            return click.prompt(f"Enter {secret} to sign metadata", hide_input=True)

        signer = Signer.from_priv_key_uri("hsm:", key, secret_handler)
        md.sign(signer, True)

    def _write(self, role: str, md: Metadata) -> None:
        filename = self._get_filename(role)

        data = md.to_bytes(JSONSerializer())
        with open(filename, "wb") as f:
            f.write(data)
        if role == "root":
            with open(self._get_versioned_root_filename(md.signed.version), "wb") as f:
                f.write(data)

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
        for key in self._get_keys(role, md.signed):
            if self.user_name != key.unrecognized_fields["x-playground-signer"]:
                # another signer: add empty signature
                md.signatures[key.keyid] = Signature(key.keyid, "")
            else:
                self._sign(md, key)

        self._write(role, md)

    def sign(self, role: str) -> None:
        md = self.open(role)
        for key in self._get_keys(role, md.signed):
            if "x-playground-signer" not in key.unrecognized_fields:
                continue
            if self.user_name != key.unrecognized_fields["x-playground-signer"]:
                continue
            # TODO the caller should know when it wants to sign: this check should not exist
            if key.keyid not in md.signatures or md.signatures[key.keyid].signature == "":
                self._sign(md, key)

        self._write(role, md)

    def update_targets(self, role: str, target_files: Dict[str, TargetFile]) -> None:
        with self.edit(role) as targets:
            if target_files == targets.targets:
                raise AbortEdit("Skipping unneeded edit")

            targets.targets = target_files

    @property
    def targets_infos(self) -> Dict[str, MetaFile]:
        raise NotImplementedError

    @property
    def snapshot_info(self) -> MetaFile:
        raise NotImplementedError
