

# Downloader client API: Napkin design

## Supported features

* list releases (versions) for project/artifact
* download specific version of artifact
* download "current" version of artifact

Note that pypi hides the "project" from downloader completely: artifact names are not namespaced in any way so project "tuf" could upload an artifact named "requests" and pip would then serve it as "requests"... This feels like a design mistake that we may not want to reproduce (although it is possible). I would rather use a model where artifact lookup requires a project name but the project name defaults to artifact name: so asking for newest version of "tuf" really means asking for newest version of the artifact "tuf" in project "tuf".


## TUF Repository design -- from client perspective

* Project and artifact names are used as parts of TUF targetpaths
* "/" is not valid in a name as we want to use that as targetpath delimiter
* Project "projectA" metadata gets a delegation "projects/projectA/*"
* Multiple artifacts per project can be supported in future but initially
  there is a default artifact name that matches the project name
  To search for non-default artifacts, client needs both project and artifact name as input.
* every artifact targetpath listed in project metadata is expected to match format
      "projects/projectA/prodB-X.Y.Z"
  where X.Y.X is three version numbers. This would allow a client to
  find artifact versions by just looking at the projects metadata...
* However, to make searching simpler we include the artifact/version
  data in a "project index" that is a TUF target file with targetpath:
      "projects/projectA/index"
  This index file contains JSON describing the artifacts the project provides:
      {
       "productB": {
         "versions": ["X.Y.Z", ... ]
       },
      }
  This duplicates info that is already in the metadata but this is easy
  for the application to access

Example target paths for "projectA"
    projects/projectA/index -- the index file
    projects/projectA/projectA-0.0.1 -- a release of default artifact
    projects/projectA/projectA-0.1.0 -- current release of default artifact
    projects/projectA/prodB-1.0.0 -- current release of another artifact

## Client implementation Notes

### list releases of product:

* input: project name 

Download project index file "projects/<project_name>/index", then output product releases parsed from the index file

### download specific version of artifact:

* input: artifact name, version (optional: project name, default is artifact name)

Form targetpath "projects/<project_name>/<artifact_name>-<X.Y.Z>", download the target

### download current version of artifact:

* input: artifact name (optional: project name, default is artifact name)

Download project index file  "projects/<project_name>/index", find
highest version number of "<artifact_name>". 
Form targetpath "projects/<project_name>/<artifact_name>-X.Y.Z",
download the target.

