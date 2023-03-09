# Repository Playground

This is a place to develop workflows and Best Practices for community artifact repositories (like PyPI or npm). To accomplish that we intend to implement a community repository of our own: A service that works like "real" artifact repositories like PyPI but is able to experiment more freely.

Current active milestone for the project is to implement a _TUF repository on a CI system_ but this goal will evolve over time.

If you'd like to reach out, you can file an issue in this project or come and say hi on [slack](https://cloud-native.slack.com/archives/C04SHK2DPK9). Any mail sent to jkukkonen at google.com will also be read, sooner or later.

## Why build this?

Community repositories have two goals that conflict with each other:

* The projects are conservative for good reasons: They are crucial parts of a vast number of supply chains, and value stability very highly. "Prototyping" is not something they are generally interested in.
* On the other hand, many of their workflows and processes were designed in a more innocent time. Updating those workflows to match modern security requirements may require changes that are not mere bug fixes: prototyping and path finding are required to find optimal solutions.

Repository playground is a place to do some of the prototyping and path finding that is required to build modern and secure Community repositories.

## Why start with TUF and trust delegation?

We're hoping Repository playground is used to solve other security problems that are shared by Community repositories, but have decided to start by tackling the problem of "trust delegation with cryptographic signatures" because of two reasons:

* The security improvement is significant: Most importantly TUF can ensure that a compromise of the repository infrastructure does not lead to end-user device compromise
* Implementing TUF in this context is not trivial: Without a concentrated effort this is unlikely to happen in the repository projects themselves

More details in [documentation](docs/):
 * [Current milestone: TUF-on-CI](playground/)
 * [Concept](docs/CONCEPT.md)
 * [TUF roadmap](docs/TUF-ROADMAP.md): How we plan to get to _secure and usable developer signed artifact repository_.
 * [TUF Design Questions](docs/TUF-DESIGN-QUESTIONS.md): What are some of unexplored issues with TUF in the community artifact repository use case
 * [TUF Design Notes](docs/DESIGN-NOTES.md): Some very early design discussion on what to build
