from typing import Dict, Iterable, List, Optional
import click
import requests

# The repository is maintained at
# https://jku.github.io/playground-baseline/
# and published to BASE_URL:
BASE_URL = "https://jku.github.io/playground-baseline/repository"


def _fetch_index(project: str) -> Optional[Dict]:
    """Fetch a project index json file, if one exists"""
    r = requests.get(f"{BASE_URL}/{project}/index.json")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _version_sort(versions: Iterable) -> List:
    """Sort list of strings using version number sort"""
    versions = list(versions)
    versions.sort(key=lambda s: [int(u) for u in s.split(".")])
    return versions


def _find_current_artifact(versions: Dict) -> Optional[str]:
    """Return current version string when given a dict where keys are version strings"""
    if not versions:
        return None

    version_strs = _version_sort(versions.keys())
    return versions[version_strs[-1]]


def _download_artifact(project: str, artifact: str) -> str:
    """Download and store artifact from given project"""
    r = requests.get(f"{BASE_URL}/{project}/{artifact}")
    r.raise_for_status()
    with open(artifact, "wb") as f:
        f.write(r.content)
    return artifact


@click.group()
def main() -> None:
    pass


@main.command()
@click.argument("product", required=True)
def download(product: str):
    # Figure out project name, product name and version
    version = None
    if "=" in product:
        product, version = product.split("=")
    project = product
    if "/" in product:
        project, product = product.split("/")

    print(f"Downloading {project} / {product} = {version}...")

    index = _fetch_index(project)
    if not index:
        raise click.ClickException(f"Project {project} not found.")

    versions = index.get(product)
    if not versions:
        raise click.ClickException(f"Product {product} not found.")

    if version is None:
        artifact = _find_current_artifact(versions)
    else:
        artifact = versions.get(version)

    if not artifact:
        raise click.ClickException(f"Version {version} not found.")

    filename = _download_artifact(project, artifact)

    print(f"Downloaded {filename}")


@main.command("list")
@click.argument("project", required=True)
def list_(project: str):
    print(f"Listing releases for {project}...")

    index = _fetch_index(project)
    if not index:
        raise click.ClickException(f"Project {project} not found.")

    for product, versions in index.items():
        if not versions:
            continue
        # print versions in sorted order
        version_strs = _version_sort(versions.keys())
        print(f"* {product}={version_strs[-1]}, all releases: {version_strs}")


if __name__ == "__main__":

    main()
