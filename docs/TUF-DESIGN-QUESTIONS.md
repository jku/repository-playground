# TUF in community artifact repositories: design questions

This document assumes we are trying to implement a system that is safe from repository compromise: A TUF installation where the artifacts are protected by a chain of offline keys. This would be a major improvement over current model where compromise of e.g. pypi.org infrastructure could result in downloader clients downloading compromised artifacts.

TUF presents a solution to repository compromise but there are multiple design questions that I believe have not been solved around the TUF repository User Experience: 
* The whole concept of local signing keys is alien to currently existing artifact repository workflows (e.g. processes that Python developers currently follow to maintain PyPI projects).
* The TUF implementations that currently exist all try to provide a "generic" TUF toolbox: this is a reasonable approach to simpler setups but not adequate for the community artifact repository use case because in this use case the gap from "toolbox" to "functioning repository" is far, far too wide.
* Implementing TUF _will_ affect the repository workflows in a fundamental way. As a result those community repository workflows need to be part of the design from the start: assuming that repositories will just adapt to some "ideal TUF workflow" is unrealistic.

Some specific issues are listed below

## Private keys vs UX

As an example of the problem with private keys, think of the “yank” functionality in PyPI: it is currently just a button on the Web UI – in our TUF model this change would have to be signed with keys that are on the developers device.

The same issue comes up with virtually every modification to the repository: 
* we need local tools that are able to "construct the changeset", sign it and send it to the repository
* the repository needs to be able to "review the change" and decide whether to accept it or not


## Project key modifications vs “chain of offline keys”

PEP-480 defines a chain of offline keys (root->targets->claimed->project) but does not adequately discuss the implications: it means that any project key changes (like adding a maintainer) require a _repository admin to sign the changes with their offline key_. This seems unacceptable to both administrators (because of work load) or developers (because key changes now take weeks).

We need to find out whether a chain of offline keys is possible with a modified design – chain of offline keys is desirable, but PEP-480 does not look like a design stakeholders will accept.

## Signature thresholds

Supporting thresholds > 1 is by no means necessary for initial implementation but even the concept might have serious implications on the design: we will have to consider this from the start.

Specifically, any local developer or admin tools need to be able to handle repository changes that are not complete: A developer must be able to create a change and make it available to other developers for them to sign

## Validating input in repository

The naive implementation of a local developer/admin tool just sends a complete new metadata file to the repository. This may not be easy for the repository to validate – do the changes look like “reasonable changes” or is this a change that should be declined?

An alternative is to define the changes in a simpler, easier to validate format: then both ends could validate the changes against current signed metadata and less trust is needed. This means the repository<->tool API becomes more important: it’s not just exchanging metadata files but defines a more refined API.

## Validating input in local developer tool

We should not expect developers to ever read TUF metadata. Yet we must make sure the local tool does not just blindly trust the repository: just taking metadata from the repository and signing it would be counter productive.


