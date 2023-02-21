## CI tools for Repository Playground

### Installation

Development install: `pip install -e .`

### Usage

These commands are used by the signing-event GitHub action.

`playground-request-signatures <known-good-directory> `: Updates the .signing-event-state file
with signature requests for all roles that have been changed (when repository directory is 
compared to known-good-directory)

`playground-status <known-good-directory> <event-name>`: Prints status of the signing event
based on the changes done in the signing event, the signature requests and invites in 
.signing-event-state file