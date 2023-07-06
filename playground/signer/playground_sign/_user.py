import click
import sys
from configparser import ConfigParser
from securesystemslib.signer import Key, Signer


def bold(text: str) -> str:
    return click.style(text, bold=True)


class User:
    """Class that manages user configuration and stores the signer cache for the user"""

    def __init__(self, path: str):
        self._config_path = path

        self._config = ConfigParser(interpolation=None)
        self._config.read(path)

        # TODO: create config if missing, ask/confirm values from user
        if not self._config:
            raise click.ClickException(f"Settings file {path} not found")
        try:
            self.name = self._config["settings"]["user-name"]
            self.pykcs11lib = self._config["settings"]["pykcs11lib"]
            self.push_remote = self._config["settings"]["push-remote"]
            self.pull_remote = self._config["settings"]["pull-remote"]
        except KeyError as e:
            raise click.ClickException(f"Failed to find required setting {e} in {path}")

        # signing key config is not required
        if "signing-keys" in self._config:
            self._signing_key_uris = dict(self._config.items("signing-keys"))
        else:
            self._signing_key_uris = {}

        # signer cache gets populated as they are used the first time
        self._signers: dict[str, Signer] = {}

    def get_signer(self, key: Key) -> Signer:
        """Returns a Signer for the given public key

        The signer sources are (in order):
        * any configured signer from 'signing-keys' config section
        * for sigstore type keys, a Signer is automatically created
        * for any remaining keys, HSM is assumed and a signer is created
        """

        def get_secret(secret: str) -> str:
            msg = f"Enter {secret} to sign"

            # special case for tests -- prompt() will lockup trying to hide STDIN:
            if not sys.stdin.isatty():
                return sys.stdin.readline().rstrip()

            return click.prompt(bold(msg), hide_input=True)

        if key.keyid in self._signers:
            # signer is already cached
            pass
        elif key.keyid in self._signing_key_uris:
            # signer is not cached yet, but the uri was configured
            uri = self._signing_key_uris[key.keyid]
            self._signers[key.keyid] = Signer.from_priv_key_uri(uri, key, get_secret)

        elif key.keytype == "sigstore-oidc":
            # signer is not cached, no configuration was found, type is sigstore
            self._signers[key.keyid] = Signer.from_priv_key_uri(
                "sigstore:?ambient=false", key, get_secret
            )
        else:
            # signer is not cached, no configuration was found: assume Yubikey
            self._signers[key.keyid] = Signer.from_priv_key_uri("hsm:", key, get_secret)

        return self._signers[key.keyid]

    def store_signer(self, uri: str, key: Key) -> None:
        """Store the uri in the signing-keys section of the config file"""
        # NOTE that this currently rewrites the whole config file, removing all comments
        # Maybe we should not store key details in this file but in a separate
        # application data file that is not really user visible?

        # NOTE Currently we set the uri and commit to a file immediately:
        # it might make sense to separate these steps so that we could only commit
        # if the whole process is successful (e.g. no git issues or something)

        self._signing_key_uris[key.keyid] = uri

        if "signing-keys" not in self._config:
            self._config.add_section("signing-keys")
        self._config["signing-keys"][key.keyid] = uri

        with open(self._config_path, "w") as f:
            self._config.write(f)
