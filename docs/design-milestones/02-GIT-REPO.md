## Git-based TUF repository

This is an example of a TUF repository built on top of Git: the concept is
largely based on Sigstore TUF repository and tries to improve on that design.

Features:
* Online repository on CI platform
* Offline threshold signing with a small signing client
* Client-repository interaction happens via GitHub PRs
* Heavily leverages CI for communication and threshold signing
* Aimed at repositories with relatively few signers and low target change
  frequency. 

More docs in [../playground/]
