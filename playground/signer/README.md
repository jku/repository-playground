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
pull-remote = origin
push-remote = origin
```

### Usage

When a signing event (GitHub issue) requests your signature, run `playground-sign`.
