# Future plans

## Actions (or reusable workflows -- undecided)

The project should provide these actions

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
   * can we audit log this?
   * maybe push the repository version files to hosting -- or just make the
     repository version a result of this action, and leave the upload
     a separate step


## events that trigger actions / workflows defined in the actual TUF reporepository

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


