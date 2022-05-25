
# Repository Playground Concept

## Problem statement

Existing community repository projects (like PyPI) have identified problems in their supply chain security but fixing those problems has been dismally slow:

* These projects are conservative for a reason: PyPI serves 500m packages every day. Interruptions are unacceptable
* Improvement attempts often fail to make convincing integration plans: as prime examples, the PEPs for implementing TUF in PyPI include almost no integration design plans -- details about how the plan will affect repository operations. The reality of these integrations (especially TUF with developer signing) is that repository workflows are likely to be disrupted significantly.

Evolutionary improvements are doable within the real repository projects (such as PyPI) but exploratory work and path finding tasks _within those projects_ do not seem like a way forward: the need to experiment and the requirement to not disrupt operations are in direct conflict with each other.

## Potential Solution

If we were to set up a new _reference artifact repository project_, we might be able to side step these issues. We could develop working processes in this reference artifact repository: After the solutions are shown to work, advocating those same ideas to community repositories will be easier, and enabling similar or same features in those repositories is no longer exploratory work but (re-)implementation.

The core idea here is a new project that implements a specific content repository (much like the real world repositories like PyPI but smaller in scale): The project documents the decisions made as well as the processes and components used to implement a “best practice community content repository” that is demonstrably more secure than current repositories are. The goal is to be able to experiment and implement these processes and components much faster than an existing repository like PyPI can.

In practice I expect we will have a repository reachable over the internet, a downloader client (akin to package managers like pip), tools for developers/package owners, and defined workflows for maintaining the repository.

## Goals

**Working content repository that implements best practices**. This should be an example for real content repositories to compare against or to copy processes and implementation details from. 

**Solve specific needs with realistic solutions**: The processes we suggest should be something content repository maintainers actually want -- not theoretical designs. This should specifically not be a TUF project but a collection of solutions for content repository problems that may use TUF as a building block.

**Measurable progress**: We must be able to decide periodically if our solutions meet this criteria, or if we should look for new ones.

## Why start with a TUF implementation?

There are multiple problems shared by most community artifact repositories: as an example of another potential case, workflows for developer signing with short lived signing certificates is certainly something many repositories would be interested. 

the reason we are focusing on making the repository compromise resilient with TUF as the _first_ task is that a highly secure TUF implementation is likely to impact workflows quite a bit -- experimenting with that first seems like a good starting point.

