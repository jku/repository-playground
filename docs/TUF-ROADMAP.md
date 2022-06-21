# TUF implementation roadmap

The goal of the TUF implementation in Repository Playground is "TUF developer signing we can show to other engineers working in the space as a demonstration". This end goal is far enough that we'll need a roadmap to get there.

The plan is to work in fairly small milestones: each milestone should
* form a functional TUF repository design
* have documentation that describes the design and security properties
* be a little more secure or featureful than the previous milestone and 
* be a little bit closer to the final goal

This means some milestones may not always move the project directly towards the end goal: Easily reachable and functional milestones are more important than progress towards final goal.

There is no need to have every milestone defined in the beginning: It's fine if we can see a few milestones ahead.

# Milestones

This is a list of achieved milestones and current view of some planned near-future milestones.

* ✓ Milestone 0: baseline repository. See [BASELINE design](BASELINE.md).
  - An approximation of current repositories without TUF (like PyPI)
  - A client and a published repository is provided
  - No tools for editing or maintenance
* Milestone 1: Minimal TUF
  - A client and a published metadata repository is provided
  - No tools for metadata editing or maintenance
  - Repository (metadata) is produced and stored manually with unspecified tools
  - Repository (metadata) design aims for the most minimal one
* Milestone 2: Timestamps
  - Timestamping server side functionality
  - The server runs on the cloud, there is a key management solution
  - Repository (metadata) is still otherwise produced and stored manually with unspecified tools
* Milestone 3: Minimal uploads
  - A server-side API that allows uploading new versions of existing metadata: at least adding and removing target files should be possible
* Milestone 4: Upload tool
  - A client-side developer tool that can upload new targets and metadata versions

