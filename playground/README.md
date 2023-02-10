# CI-based TUF implementation

This is a TUF implementation that operates on Continuous Integration platform.
Supported features include:
* Threshold signing with offline keys, guided by CI
* Automated online signing
* Streamlined, opinionated user experience
* No custom code required

The optimal use case (at least to begin with) is TUF repositories with a low
to moderate frequency of change, both for target target files and keys.

## Documentation

* Design document: TODO: share this and add link
* [Implementation notes](IMPLEMENTATION-NOTES.md)

## Setup & operation

TODO Document:
* How to start a new TUF repository
* How to modify delegations 
* How to modify target files

## Components

### Repository template

Status: TODO, very rough prototype exists in playground/signer in this repository.

Intent is to setup a new git repository for this.

### Repository actions

Status: TODO, very rough prototype exists in https://github.com/jku/playground-git-demo
and playground/repo directory in this repository.

Intent is that
* actions are maintained in this git repository, e.g. actions/signing-event/action.yml
* the software the actions use is maintained in this repository in playground/repo/

### signing tool

Status: TODO, prototype exists

Intent is that the signer tools is maintained in this repository in playground/signer/

### Client

`client/` contains a simple downloader client. It can securely lookup and download artifacts from the repository.
There is nothing specific to this repository implementation in the client implementation: any other client could be used. 

TODO: review whether "list" is something we want to support or not.