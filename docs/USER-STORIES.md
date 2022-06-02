# User stories for Reference Content Repository

A rough outline of what the repository should offer: this should be a minimal feature set but still comparable to a real community artifact repository.

The user categories are:
* Downloader (pip user in the Python ecosystem)
* Admin (pypi.org admin in the Python ecosystem)
* Project Maintainer (Python package maintainers in the Python ecosystem)

## Downloader User

### “Download ABC release X.Y.Z”

User wants a specific release of project ABC.

### “Download latest ABC release”

User wants the newest release of project ABC.

### “List ABC release versions”

User wants to see what release of project ABC are available.

## Repository Admin

### “Initialize repository”

Admin wants to create a new repository.

### “Modify configuration”

Admin wants to modify configuration of the system.

###  “Block trust delegation”

Admin wants to prevent a project from spreading malware: Stop serving some (or all) published artifacts and possibly prevent the project from releasing any artifacts.

## Project maintainer

### “Create Project (delegation)”

A new maintainer wants to create a new project in the repository, reserving the project name: This delegates trust from the repository to the maintainer for this specific project.

This is a special case in that it is a "write" action but the repository does not necessarily have any existing relationship with the maintainer: in essence new project creation is available to anyone on the internet.

**For TUF this is a special case as well: every other action is "authorized" by the fact that the change is signed by correct keys... In this case we want to add new keys and create a new delegation without the proposed change being signed by any keys**

### “Add/remove maintainers to a project”

Maintainer wants to add a new maintainer to the project, remove an existing maintainer or change the authentication mechanism for an existing maintainer.

**For TUF This is maybe the most interesting story: it requires modifying delegating metadata but also needs to be automated – PEP480 does not solve this problem**

### “Add new release to a project”

Maintainer wants to upload a new release artifact.

### “Remove a release”

Maintainer wants to remove or at least prevent downloads of an existing artifact

### “Approve a change made by another maintainer”

Maintainer wants to approve a change made by another maintainer.

**This use case assumes the repository supports "threshold of maintainers" for specific actions**

### “See current project state”

Maintainer wants to see details of a project: what artifacts are are available, who the maintainers are, etc.

## Major open questions for TUF implementations of these use cases

### How are maintainers able to add/remove maintainers?

This is pretty critical: Adding/removing maintainers (keys) means modifying the **delegating** metadata. With the PEP-480 metadata structure that means metadata signed by repository admins, not the project maintainers.

This is not realistic: Repository admins cannot start signing targets changes for every project key modification. A multi-level project metadata structure would make it at least possible… still might not be reasonable for repo admins.

### Approving changes made by other maintainers

This is a feature current repository implementations do not have, but it is something TUF would enable. The practical implementation might not be trivial though.

How does a maintainer know there is a change from another maintainer  to sign? How do they refer to the change? How do they review the change for correctness? The developer tool can’t just trust the server on this: it must assume the repository is compromised. The new metadata should probably be available via normal metadata download: just not part of official snapshot yet – so that there is a single possible “next version” of metadata that can either be A) overwritten or B) multisigned.

### API definitions

Both client and developer APIs need to be developed based on these use cases to find any remaining issues: this has not yet been done.

