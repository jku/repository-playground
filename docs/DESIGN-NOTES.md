# Community Artifact repository with TUF: Design notes


This is _not_ a design document, just some initial notes.

The core assumption here is that 
* we want to build a system that is resilient to repository compromise to a degree where attackers gaining control of the repository software and database would not give them ability to feed downloading clients malicious files.
* We are going to use TUF with developer signing to implement this

Implementing a complete community artifact repository like that is not a small task:
* We should divide this task into subproject
* We should aim to implement these subprojects as Minimum Viable Products and improving them as required

we should consider following subprojects:

## Repository design (client POV)

What does our repository provide to downloaders? Just bare bones targets download would be easiest to implement but almost no-one is interested in that alone. We likely want to define at least a versioning scheme from the beginning so that it’s possible for a client to do the common actions like 
* “list all releases of project ABC” and 
* “download project ABC release X.Y.Z”.

These will require some design as TUF itself does not provide this. 

[Repository design, client POV](TUF-CLIENT-DESIGN.md)

## Define the supported (developer/admin) user stories

Before we can design an API and the tool that uses the API, we need to have a comprehensive view of the things we want to support. Defining them is likely the most important piece of this project.

## Define API (for the local developer/admin tool)

There should be an API for developer/maintainer changes: it should enable developers and maintainers to safely do all of the things that the TUF model requires signatures for, without forcing those developers/maintainers to understand how TUF works.


## Implement developer/admin tool (for modifying and signing metadata)

We need a tool that can manage things like 
* New target upload
* Yank target
* Add new maintainer
* Create a new project
* Sign a change done by another developer
* ...

The tool should not require the developer to be able to review the actual metadata JSON.

## Repository design (storage)

Decide how to store metadata, configuration (and the actual artifacts): 
* A database would mimic how PyPI works but using git as a database could provide us with great visibility and ability to debug.
* private key storage: If we manage to design a fully-offline-chain-of-keys this is less important but the online keys still need to to be stored somewhere

## Web UI

I believe the project is going to require a repository UI of some kind to visualize the repository state: command line tools are not enough. However, it may be possible that the UI does not have to be interactive: it could be just static pages with each page representing one metadata file.

A simple TUF web UI would be great for the ecosystem in general: we should try to make it a generic component.
