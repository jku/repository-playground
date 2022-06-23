# Minimal TUF repository

This is the Minimum Viable TUF implementation:
* Metadata structure is the simplest possible
* Only two active roles (keys): root and repository admin
* No maintenance tools: repository admin is expected to edit metadata using other unspecified methods
* repository admin stores metadata in git, this is automatically published to downloader clients HTTP endpoint
* A downloader client is provided in this repository, see playground/README.md for usage.

## Security

The advantages over baseline repository are:
* Storage security is non-critical: A compromise of metadata git or the published metadata can not compromise a client as the client only downloads content that has been verified with trusted keys
* Compromise of repository admin keys is recoverable
* A rollback attack (offering old versions of artifacts to clients) is mitigated in case of storage compromise


## Repository metadata design

Metadata matching this design is maintained in https://github.com/jku/playground-tuf-minimal/

The design forfeits the advantages that snapshot and timestamp would typically provide in exchange for simplicity:  Expiry dates are set far into the future and a single key ("repository admin key") signs for timestamp, snapshot and targets. this means no "cloud" functionality is required and metadata changes only happen when the repository admin adds or removes artifacts.

The repository exposes the same content structure as the baseline design: A repository contains projects, projects contain products, products have versioned artifacts. This structure is exposed in artifact targetpaths: 
```
    "python-tuf/src/1.0.0/tuf-1.0.0.tar.gz"
```
This translates to project "python-tuf", product "src", version "1.0.0", artifact name "tuf-1.0.0.tar.gz".

Repository guarantees that
* All target files in the repository have targetpaths that match the structure above (with the exception of index.json files, see below)
* project, product, version or artifact strings are not allowed to contain "/" or "=" and are valid URL fragments
* projects can have multiple products, products can have multiple versions
* A project-product-version only contains a single artifact

As an added feature, every project provides a index.json file (targetpath "python-tuf/index.json") that lists the products, versions and artifacts for that project: This is information that is already parsable from the targetpaths, and must match the targetpaths.

The actual artifacts are maintained in the same git repository -- but could easily be stored elsewhere.
