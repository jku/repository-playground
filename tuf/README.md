# Minimal TUF repository and client

This is a minimal TUF repository and client setup.
TODO: Add link to to repository design doc.

See https://github.com/jku/playground-tuf-minimal for the repository content.


## Client

`client/` contains a simple (but from TUF perspective complete) client. It can securely lookup and download artifacts from the repository.

### Client usage:

```
# List product releases available for a project 'tuf-spec':
$ python playground_client.py list tuf-spec

# Download current version of default product:
$ python playground_client.py download tuf-spec

# Download another product in the project:
$ python playground_client.py download tuf-spec/tarball

# Download a specific version:
$ python playground_client.py download tuf-spec/tarball=1.0.28
```

## Repository & developer tools

No tools are provided at this point. 
