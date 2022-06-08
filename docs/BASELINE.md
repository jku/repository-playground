# Baseline repository

This is a simplified community content repository that acts as the starting point for the security improvements, such as TUF.

The concept resembles PyPI and other current repositories: authenticated project maintainers make artifact uploads, and the repository makes the uploads available to anonymous downloaders. The reality of a repository such as this is that :
* maintainer actions or repository admin actions are not visible or verifiable to the downloader client. Only repository content at time of download matters to the downloader
* The repository makes a security guarantee that any artifact URLS starting with `projectA/...` are only controlled by the maintainers of projectA (and the repository admins). This is not something downloaders can verify.
* repository admins can affect the repository content as they wish: the expectation is that they only provide content created by project maintainers but this is ensured only by internal processes not visible to downloaders.
* Artifact validity is ensured at upload time in an internal repository process by A) authenticating the uploader as a maintainer of the project and B) running heuristic checks on the artifacts (like a malware scan). This validation is also not verifiable by downloader clients

The above means that compromising the repository infrastructure allows attacker to modify repository content, and downloader clients will accept that content. Repository Playground does not intend to implement any of the upload and repository maintenance machinery because of that reason: we will only "simulate" that by creating repository content that the upload and repository maintenance machinery would have created.

## Design

The repository is just collection of directories (projects) that contain an index file and artifacts: A directory is controlled by the maintainers of that project. The index file is a json file that lists the currently published artifacts for the project: the artifacts are available in the same directory.

Example 
```
  projects/
    projectA/
      index.json
      projectA-0.0.1.tar.gz
      otherproduct-1.0.0.zip
      otherproduct-1.0.1.zip
    projectB/
      index.json
      projectB-0.0.1.tar.gz
```

projectA/index.json:

```
 {
   "projectA": {
     "0.0.1": "projectA-0.0.1.tar.gz"
   },
   "otherproduct": {
     "1.0.0": "otherproduct-1.0.0.zip",
     "1.0.1": "otherproduct-1.0.1.zip",
   },
 }
```

Client should always start by downloading `<baseurl>/projects/<projectname>/index.json`.
They can then use that content to decide which artifact to download.

Some notes on this design:
* A product can have multiple versions, project can have multiple products
* A version can only have one artifact (as in file.1.0.0.tar.gz and file.1.0.0.zip are not the same "product")
* index file does not contain hashes for the artifacts but could for a couple of reasons: 
  * security if artifacts were hosted on another host (currently no benefit here)
  * integrity to verify download succeeded
* the client has to know both project name and product name to download something
* TODO case sensitivity for project/product names?


## Implementation

As mentioned, upload or repository maintenance machinery is not going to be implemented. There will be static repository content as per design (see https://github.com/jku/playground-baseline), and a downloader client that is able to download artifacts.
