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

## Setup

Current signing requirements are:
 * A HW key with PIV support (such as a newer Yubikey)
 * Google Cloud KMS

### Setup signer

1. Create a PIV signing key on your HW key if you don't have one. [yubico-piv-tool](https://developers.yubico.com/yubico-piv-tool/) can do it (just copy-paste the public key and certificate when requested):
   ```
   yubico-piv-tool -a generate -a verify-pin -a selfsign -a import-certificate -s 9c -k -A ECCP256 -S '/CN=piv_auth/OU=example/O=example.com/'
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

### Configure signer

Whenver you run signing tools, you need a configuration file `.playground-sign.ini` in the root dir of the git repository that contains the metadata:
   ```
   [settings]
   # Path to PKCS#11 module
   pykcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
   # GitHub username
   user-name = @my-github-username
   ```

### Setup a new Playground repository

1. Fork the [template](https://github.com/jku/playground-template). Enable
   _Settings->Actions->Allow GitHub Actions to create and approve pull requests_.
1. To enable repository publishing, set _Settings->Pages->Source to `Github Actions`. `main`
   should be enabled as deployment branch in _Settings->Environments->GitHub Pages_.
1. Make sure Google Cloud allows this repository OIDC identity to sign with a KMS key.
   Insert the GCP authentication details into .github/workflows/snapshot.yml

## Operation

### Initial signing event

1. Run delegate tool to create initial metadata
   ```
   playground-delegate
   ```
1. Commit all changes in `metadata/`, push to a branch `sign/<signing-event-name>`

This starts a signing event.

### Modify target files

1. Add, remove or modify files under targets/ directory
1. Run signer tool
   ```
   playground-sign
   ```
1. Commit changes (both target files and metadata) and push to a branch `sign/<signing-event-name>`

This starts a signing event.

### Add a delegation or modify an existing one

1. Run delegate tool when you want to modify a roles delegation
   ```
   playground-delegate <role>
   ```
1. Commit all changes in `metadata/`, push to a branch `sign/<signing-event-name>`

This starts a signing event.

### Sign changes made by others

Signing should be done when the signing event (GitHub issue) asks for it:

1. Run signer tool in the signing event branch
   ```
   playground-sign
   ```
2. Commit metadata changes and push to a branch `sign/<signing-event-name>`

This updates the signing event.

## Components

### Repository template

Status: partially implemented in the playground-template project.
* Currently only contains signing event workflow

See [https://github.com/jku/playground-template]

### Repository actions

Status:
* *actions/signing-event*: functionality is there but output is a work in progress, and
  various checks are still unimplemented 
* *actions/snapshot*: Implemented
* *online-version-bump*: Implemented
* *offline-version-bump*: Implemented, but the signing event does not currently trigger

Various parts are still very experimental
* loads of content safety checks are missing
* output of the signing event is a work in progress
* failures in the actions are not visible to user

See [repo/](repo/), See [actions/](actions/)

### signing tool

Status:
* playground-delegate mostly implented
* playground-sign mostly implemented

See [signer/](signer/)

### Client

`client/` contains a simple downloader client. It can securely lookup and download artifacts from the repository.
There is nothing specific to this repository implementation in the client implementation: any other client could be used. 

TODO: Client is currently not up-to-date WRT repository implementation.
