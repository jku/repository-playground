# User stories for Reference Content Repository

A rough outline of what the repository should offer: this should be a minimal feature set but still comparable to a real community artifact repository.

The user categories are:
* Downloader (pip user in the Python ecosystem)
* Admin (pypi.org admin in the Python ecosystem)
* Project Maintainer (Python package maintainers in the Python ecosystem)

## Downloader User

### “Download ABC release X.Y.Z”

User wants a specific release of project ABC 

### “Download latest ABC release”

User wants the newest release of project ABC 

### “List ABC release versions”

User wants to see what release of project ABC are available 

## Repository Admin

### “Initialize repository”

Admin wants to create a new repository.

### “Modify top level metadata”

Admin wants full control over the metadata: e.g. change consistent_snapshot, add custom metadata. This likely requires ability to upload complete metadata files

This change could require additional signatures to be valid.

### “Modify top level keys”

Admin wants to add, remove or replace keys: either offline or online toplevel keys.

This change could require additional signatures to be valid.

### “Modify configuration”
Admin wants to modify configuration of the system that is not by TUF spec part of the metadata
(e.g. when to run timestamp process).

###  “Block a delegation (prevent metadata from being served)”

Admin wants to prevent a project from spreading malware: either stop delegation completely or something else (? maybe modify the delegation to exclude some targets?)

This change could require additional signatures to be valid.

## Project maintainer

### “Add new Project (delegation)”

A new maintainer wants to create a new project in the repository, reserving the project name

This is a special subcase of “Modify keys for delegated metadata”

### “Modify keys/threshold for a project”

Maintainer wants to add a new maintainer to the project, remove an existing maintainer's key or change the key for an existing maintainer.

This change could require additional signatures to be valid.

**This is maybe the most interesting story: it requires modifying delegating metadata but also needs to be automated – PEP480 does not solve this problem**

### “Add new release (a target to delegated metadata)”

Maintainer wants to upload a new release, and add target to delegated metadata

This change could require additional signatures to be valid.

### “Remove a release (a target from delegated metadata)”

Maintainer wants to remove or block the download of an existing release

This change could require additional signatures to be valid.

### “Sign a change made by another maintainer”

Maintainer wants to approve a change made by another maintainer

### “See current project state”

Maintainer wants to see what targets are available, who the maintainers are, what are the key/threshold settings. This is a preliminary part of every other story.

This could be done with a website – but it’s good to acknowledge that the website output would not be protected by TUF... Some project state might have to be available via means protected by TUF. 


## Major open questions

### How are maintainers able to modify keys for the project?

This is pretty critical: Repository admins can’t start signing targets changes for every project key modification. A multi-level project metadata structure would make it at least possible… still might not be reasonable for repo admins

### multisig

How does a maintainer know there is a change from another maintainer  to sign? How do they refer to the change? How do they review the change for correctness? The developer tool can’t just trust the server on this: it must assume the repository is compromised. The new metadata should probably be available via normal metadata download: just not part of official snapshot yet – so that there is a single possible “next version” of metadata that can either be A) overwritten or B) multisigned

### API definitions

Both client and developer APIs need to be developed based on these use cases to find any remaining issues: this has not yet been done.

