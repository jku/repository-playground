# Notes for implementation

## Signer tool Commands

Most actions should require no arguments or even commands. The tool
  should offer the right thing based on context
  * accept invitation -- offered when user is in "role.invites" custom metadata
  * update targets -- offered when the targets/ dir does not match targets in metadata
  * bump metadata -- offered when the expiry is getting closer
  * sign changes -- offered when user is a signer and the sig is missing
  * initialize a repository -- offered when root.json does not exist yet (but see below)

Some actions require input
  * change delegation:
    * role, signers/keys, threshold, expiry-period, signing-period
  * initialize a repository -- this is a special case of 4 X change delegation with some defaults

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
* role.expiry-period & role.signing-period
  * used by repo to decide when new timestamp/snapshot is needed and to decide the new expiry date
  * for other roles could be used to decide what expiry dates are allowed by repo
* signed.expiry-period & signed.signing-period (_could_ be in signed, but maybe in role to tie with other delegation changes)
  * used by repo to decide when to start a signing event
  * used by tool to bump version

## How much to automate in signer 

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

## GitHub Actions that should be provided

1. online-sign
  * if snapshot is needed, create one. If timestamp is needed, create one
  * Smoke test? -- make sure the repository is considered valid and updatable by clients
  * merge to main (or create PR, this could be configurable)
2. signing-event
   Uses repo software to define the state of the signing event.
   Possible signing event states include:
   * No actual changes (branch has been created, but no commits)
   * Changes to online roles (error)
   * Changes to offline roles, not accepted by repository (error)
     * metadata changes don't match target file changes
     * unexpected expiry date
     * unexpected delegation structure
     * etc, etc
   * Signer invitations waiting
   * Changes to offline roles, at least one roles threshold not reached
   * Thresholds reached
   Two possible results
   * Document current state with a comment in issue in TUF repository
   * If thresholds have been reached, also create a PR in TUF repository
3. publish
   * use repo software to create a repository version
   * can we audit log this somehow -- this is the relevant event for the public repository 
   * make the repository files a result of this action, and leave the upload
     to the calling workflow

## CI events that trigger actions / workflows defined in the repository template 

All actions should take at least metadata dir as argument

### signing-branch-changed

* This event means a signing-event branch in the repository has changed
* workflow calls external action "signing-event"

### main-changed, cron

* Same process happens after every signing event merge and periodically
* workflow calls external action "online-sign":
* If online-sign changed anything, workflow calls external action "publish"
* take the results of "publish", push them to github pages

### label-assigned

* This is a convenience to create a branch for external contributors
* if "sign/..." label is assigned to an issue, create a signing event branch of same name

