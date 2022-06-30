# Minimal TUF repository

This is the Minimum Viable TUF implementation:
* Metadata structure (maintained at https://github.com/jku/playground-tuf-minimal/) is the simplest possible
* Only two active roles (keys): root and repository admin
* No "server" functionality: Metadata is not modified by any online processes, only by the repository admin
* No maintenance tools: repository admin is expected to edit metadata using other unspecified methods (https://github.com/vmware-labs/repository-editor-for-tuf was used in practice)
* repository admin makes metadata changes and signs the changes locally, pushes the changes to a remote git repository: this is automatically published to downloader clients HTTP endpoint
* A downloader client is provided in this repository, see playground/README.md for client usage.

## Security

The repository admin key is required to add or remove artifacts (in a way that clients would accept). Root key is required to update the repository admin key.

The advantages over baseline repository are:
* Storage security is non-critical: A compromise of repository content (either artifacts or metadata) can not compromise a client as the client only downloads artifacts verified with trusted keys
* Compromise of repository admin keys is recoverable
* A rollback attack (offering old versions of artifacts to clients) is mitigated in case of storage compromise


## Repository metadata design

Metadata matching this design is maintained in https://github.com/jku/playground-tuf-minimal/

The design forfeits the advantages that TUF snapshot and timestamp would typically provide in exchange for simplicity:  Expiry dates are set far into the future and a single key ("repository admin key") signs for timestamp, snapshot and targets. this means no "cloud" functionality is required and metadata changes only happen when the repository admin adds or removes artifacts.

The repository exposes the same content structure as the baseline design: A repository contains projects, projects contain products, products have versioned artifacts. This structure is exposed in artifact targetpaths: 
```
    "python-tuf/src/1.0.0/tuf-1.0.0.tar.gz"
```
This translates to project "python-tuf", product "src", version "1.0.0", artifact name "tuf-1.0.0.tar.gz". This targetpath structure means the client is able to search for specific artifacts using the metadata that contains the targetpaths.

Repository guarantees that
* All target files in the repository have targetpaths that match the structure above
* project, product, version or artifact strings are not allowed to contain "/" or "=" and are valid URL fragments
* projects can have multiple products, products can have multiple versions
* A project-product-version triplet uniquely identifies a single artifact

The actual artifacts are maintained in the same git repository -- but could easily be stored elsewhere.
