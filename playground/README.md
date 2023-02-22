# CI-based TUF implementation

This is a TUF implementation that operates on Continuous Integration platform.
Supported features include:
* Threshold signing with offline keys, guided by CI
* Automated online signing
* Streamlined, opinionated user experience
* No custom code required

The optimal use case (at least to begin with) is TUF repositories with a low
to moderate frequency of change, both for target target files and keys.

This is a Work-In-Progress: any code should be seen as experimental for now.

## Documentation

* [Design document](https://docs.google.com/document/d/140jiFHGc3wwEmNaJmUdgkNeNK4i4CC-lm5-eVQYXiL0)
* [Implementation notes](IMPLEMENTATION-NOTES.md)

## Setup & operation

Current signing requirements are:
 * A HW key with PIV support (such as a newer Yubikey)
 * Google Cloud KMS

### Setup signer

1. Create a PIV signing key on your HW key if you don't have one. This uses the Yubikey tool:
   ```
   yubico-piv-tool -a generate -a verify-pin -a selfsign -a import-certificate -s 9c -k -A ECCP256 -S '/CN=piv_auth/OU=test/O=example.com/'
   ```
1. Install a PKCS#11 module. Playground has been tested with the Yubico implementation,
   Debian users can install it with
   ```
   apt install ykcs11
   ```
1. install playground-sign
   ```
   pip install git+https://git@github.com/jku/repository-playground#subdirectory=playground/signer
   ```
1. _(only needed for initial repository creation)_ Install
   [gcloud](https://cloud.google.com/sdk/docs/install), authenticate (you need
   _roles/cloudkms.publicKeyViewer_ permission)

### Setup a new Playground repository

1. Fork the [template](https://github.com/jku/playground-template). Enable
   _Settings->Actions->Allow GitHub Actions to create and approve pull requests_.
1. Make sure Google Cloud allows this repository OIDC identity to sign with a KMS key

### Create TUF metadata (the initial signing event)

1. checkout your new git repository, create a configuration file `.playground-sign.ini` in the root dir:
   ```
   [settings]
   # Path to PKCS#11 module
   pykcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
   # GitHub username
   user-name = @my-github-username
   ```
1. create a new branch with a branch name starting with "sign/"
1. Run `playground-delegate`, answer the questions
1. Commit the changes, push to the branch
1. Follow advice in the signing event GitHub issue that gets opened

### TODO

Document:
* How to sign
* How to modify delegations 
* How to modify target files

## Components

### Repository template

Status: partially implemented in the playground-template project.
* Currently only contains signing event workflow

See [https://github.com/jku/playground-template]

### Repository actions

Status:
* actions/signing-event is partially implemented
* the CLI commands needed by actions/signing-event are partially implemented
  * playground-request-signatures
  * playground-status

Not implemented yet
* snapshot/timestamp
* cron version bumps

See [repo/](repo/), See [actions/](actions/)

### signing tool

Status:
* playground-delegate mostly implented
* playground-sign mostly implemented

See [signer/](signer/)

### Client

`client/` contains a simple downloader client. It can securely lookup and download artifacts from the repository.
There is nothing specific to this repository implementation in the client implementation: any other client could be used. 

TODO: review whether "list" is something we want to support or not.