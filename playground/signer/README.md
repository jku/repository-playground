This is a very Work-In-Progress "signing tool" for a git-based TUF-repository


Usage:

# Make sure you have a PIV signing key on your hardware key
https://github.com/secure-systems-lab/securesystemslib/issues/494

# Find the pkcs library (this path works on debian after installing ykcs11)
export PYKCS11LIB=/usr/lib/x86_64-linux-gnu/libykcs11.so

# initialize the repository
./tool init


# Future plans

## Commands

Most actions should require no arguments or even commands. The tool
  should offer the right thing based on context
  * accept invitation -- offered when user is in "role.invites" custom metadata
  * update targets -- offered when the targets/ dir does not match targets in metadata
  * bump metadata -- offered when the expiry is getting closer
  * sign changes -- offered when user is a signer and the sig is missing

Some actions require a command
  * change delegation:
    * signers/keys, threshold, expiry-period, signing-period
  * init repo -- this is a special case of 4 X change delegation with some defaults

## Custom metadata 

Custom metadata and how it is used

  * key.signer-username
    * used by tool to know when to sign
    * used by repo to notify @username
  * key.online-uri
    * used by repo to sign with online key
  * role.invites
    * used by repo to notify invited usernames
    * used by tool to accept invitations
  * role.online-expiry-period
    * used by repo to decide new timestamp and snapshot expiry date
      (this could be just a workflow config as well)
  * role.signing-period
    * used by repo to decide when new timestamp/snapshot are needed
      (this could be just a workflow config as well)
  * signed.signing-period (_could_ be in signed, but maybe in role to tie with other delegation changes)
    * used by repo to decide when to start a signing event
    * used by tool to bump version

## How much to automate 

The big question is hiding git UX:
* hiding git details is not ideal: it should always be possible to leave that to user
* on the other hand, the remaining UX complexity is in branch management... Which can be simplified if the signing tool handles it

Potential automation design
* tool knows the remote names "origin" and "fork" (pull and push remotes, respectively): This requires either standardizing every maintainers setup or configuration -- probably both make sense (standard setup just works, but config is available)
* given a signing event name (branch name), the tool can now handle pulls, pushes and creating links for PRs. 
signer <signing-event>` -- this could do everything from pulling the branch, explaining changes and what is going to happen, asking for signature, creating a commit, pushing the branch, and creating a link to make a PR. This would all work for forks or maintainers working in-repo
* Required tool config
  ```
  username = @jku
  pkcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
  origin = origin
  fork = jku
  ```