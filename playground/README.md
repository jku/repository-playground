# CI-based TUF implementation

This is a TUF implementation that operates on Continuous Integration platform.
Supported features include:
* Threshold signing with offline keys, guided by CI
* Automated online signing
* Streamlined, opinionated user experience
* No custom code required

The optimal use case (at least to begin with) is TUF repositories with a low
to moderate frequency of change, both for target target files and keys.

## Status

Planning: any code should be seen as experimental.

## Documentation

* [Design document](https://docs.google.com/document/d/140jiFHGc3wwEmNaJmUdgkNeNK4i4CC-lm5-eVQYXiL0)
* [Implementation notes](IMPLEMENTATION-NOTES.md)

## Setup & operation

TODO Document:
* How to start a new TUF repository
* How to modify delegations 
* How to modify target files

## Components

### Repository template

Status: partially implemented in the playground-template project.
* Currently contains signing event workflow
* Requires enabling _Settings->Actions->Allow GitHub Actions to create and
  approve pull requests_

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

See [repo/], See [actions/]

### signing tool

Status:
* playground-delegate mostly implented
* playground-sign mostly implemented

See [signer/]

### Client

`client/` contains a simple downloader client. It can securely lookup and download artifacts from the repository.
There is nothing specific to this repository implementation in the client implementation: any other client could be used. 

TODO: review whether "list" is something we want to support or not.