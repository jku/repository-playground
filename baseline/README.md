
This is a simple baseline downloader client (to demonstrate a repository without any of the security improvements Repository Playground intends to implement). See docs/BASELINE.md for background and https://github.com/jku/playground-baseline for the repository content.

# Usage:

```
# List product releases available for a project 'tuf-spec':
$ python baseline_client.py list tuf-spec

# Download current version of default product:
$ python baseline_client.py download tuf-spec

# Download another product in the project:
$ python baseline_client.py download tuf-spec/tarball

# Download a specific version:
$ python baseline_client.py download tuf-spec/tarball=1.0.28
```
