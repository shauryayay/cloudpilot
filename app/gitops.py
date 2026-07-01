"""Commit generated config files to a local Git repo — the GitOps source of truth.

The API generates declarative config and commits it to a Git repository.
In a production setup, a GitOps controller would watch this repo and
reconcile the desired state against actual cloud resources.

Layout:

    gitops-repo/
    └── clusters/
        └── {owner}/
            └── {cluster_name}-{env}/
                ├── Chart.yaml
                └── values.yaml

Each provision request = one commit. The commit SHA is stored on the
cluster record for auditability.
"""

from __future__ import annotations

import os
from pathlib import Path

from git import Repo, InvalidGitRepositoryError

from app.config import settings


def _ensure_repo() -> Repo:
    repo_path = Path(settings.gitops_repo_path)
    repo_path.mkdir(parents=True, exist_ok=True)
    try:
        return Repo(repo_path)
    except InvalidGitRepositoryError:
        repo = Repo.init(repo_path)
        readme = repo_path / "README.md"
        readme.write_text("# GitOps Repo\n\nAuto-managed by cloudpilot.\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        return repo


def commit_provision(
    owner: str,
    cluster_name: str,
    environment: str,
    chart_yaml: str,
    values_yaml: str,
) -> str:
    """Write config files and commit. Returns the commit SHA."""
    repo = _ensure_repo()
    repo_root = Path(repo.working_dir)

    cluster_dir = (
        repo_root / "clusters" / owner / f"{cluster_name}-{environment}"
    )
    cluster_dir.mkdir(parents=True, exist_ok=True)

    (cluster_dir / "Chart.yaml").write_text(chart_yaml)
    (cluster_dir / "values.yaml").write_text(values_yaml)

    rel_chart = os.path.relpath(cluster_dir / "Chart.yaml", repo_root)
    rel_values = os.path.relpath(cluster_dir / "values.yaml", repo_root)

    repo.index.add([rel_chart, rel_values])

    commit = repo.index.commit(
        f"provision: {owner}/{cluster_name} ({environment})\n\n"
        f"Tracked by cloudpilot API"
    )
    return commit.hexsha
