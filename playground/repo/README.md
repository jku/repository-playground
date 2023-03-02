## CI tools for Repository Playground

### Installation

Development install: `pip install -e .`

### Usage

These commands are used by the signing-event GitHub action.

`playground-status <known-good-directory> <event-name>`: Prints status of the signing event
based on the changes done in the signing event and invites in .signing-event-state file

`playground-publish <dir>`: Creates a deploy-ready metadata repository in the given directory

`playground-snapshot`: Updates snapshot & timestamp based on current repository content

`playground-timestamp`: Updates timestamp based on current repository content

`playground-bump-expiring <rolename>`: Bumps the roles version if it is about to expire
