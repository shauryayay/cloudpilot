"""Generate declarative config files (Chart.yaml + values.yaml) for a cluster.

The API renders these files from the provision request and commits them to
a Git repo. In a full GitOps setup, a sync controller would watch the repo
and reconcile actual cloud resources to match the desired state.
"""

from __future__ import annotations

import yaml

from app.models import Engine, ClusterRecord


_ENGINE_PORTS: dict[Engine, int] = {
    Engine.POSTGRES: 5432,
    Engine.MYSQL: 3306,
    Engine.MONGO: 27017,
    Engine.REDIS: 6379,
}

_CHART_NAMES: dict[Engine, str] = {
    Engine.POSTGRES: "cloudpilot-postgres",
    Engine.MYSQL: "cloudpilot-mysql",
    Engine.MONGO: "cloudpilot-mongo",
    Engine.REDIS: "cloudpilot-redis",
}


def generate_chart_yaml(record: ClusterRecord) -> str:
    chart = {
        "apiVersion": "v2",
        "name": f"{record.owner}-{record.cluster_name}",
        "version": "0.1.0",
        "description": (
            f"{record.engine.value} cluster for {record.owner} "
            f"({record.environment.value})"
        ),
        "type": "application",
        "dependencies": [
            {
                "name": _CHART_NAMES[record.engine],
                "version": "1.x",
                "repository": "https://charts.example.com",
            }
        ],
    }
    return yaml.dump(chart, default_flow_style=False, sort_keys=False)


def generate_values_yaml(record: ClusterRecord) -> str:
    users_block = [
        {"name": u.name, "privileges": u.privileges} for u in record.users
    ]

    values: dict = {
        "owner": record.owner,
        "clusterName": record.cluster_name,
        "environment": record.environment.value,
        "engine": record.engine.value,
        "instanceType": record.instance_type,
        "database": record.database,
        "users": users_block,
        "deletionProtection": record.deletion_protection,
        "encrypted": True,
        "tlsEnabled": True,
        "backupRetentionDays": 7 if record.environment.value != "dev" else 1,
    }

    if record.engine in (Engine.POSTGRES, Engine.MYSQL):
        values["replicas"] = 2 if record.environment.value == "prod" else 1
        values["autoScale"] = record.environment.value == "prod"

    if record.engine == Engine.REDIS:
        values["shardCount"] = 1
        values["replicasPerNode"] = 1 if record.environment.value == "dev" else 2

    return yaml.dump(values, default_flow_style=False, sort_keys=False)


def get_port(engine: Engine) -> int:
    return _ENGINE_PORTS[engine]
