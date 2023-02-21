### Requirements

In addition to the Python requirements managed by pip, a PKCS#11 module is
required (and it's location needs to be configured, see below).

This tool has been tested with the Yubico implementation of PKCS#11, 
[YKCS11](https://developers.yubico.com/yubico-piv-tool/YKCS11/). Debian users
can install it with `apt install ykcs11`.

### Installation

Development install: `pip install -e .`

### Configuration

Tool does not currently write the config file itself so this needs to be done manually.

`.playground-sign.ini` (in the git toplevel directory):
```
[settings]
pykcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
user-name = @jku
```

### Usage

When a signing event (GitHub issue) requests your signature, run `playground-sign`.

### TODO

* version bump: Currently we bump version if there are no _uncommitted changes_ in git
  for this role. This is not optimal especially for root as a single delegation change
  can produce multiple root versions, we should bump if there are no changes yet
  _compared to signing event forking point_
* git integration. Woould be nice to be able to avoid
  * git fetch
  * git checkout <signing-event>
  * git push <remote> <signing-event>
  * _figure out how to create a PR to the signing-event
  We can do all this if we store pull-remote and push-remote information in the configuration