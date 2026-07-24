"""
Real Kubernetes remediation actions, used by app/core/remediation.py.

SAFETY MODEL:
- config.KUBE_DRY_RUN defaults to True. In dry-run mode every function
  logs exactly what it WOULD do and returns without touching the cluster.
- Even with dry-run off, every action is scoped to exactly one service via
  data/service_k8s_map.yaml - there is no "act on everything" code path.
- Kubernetes client is initialized lazily (only when an action actually
  runs), so importing this module never requires a working kubeconfig -
  useful for local dev / tests where there's no real cluster.
"""

from __future__ import annotations
import subprocess
import yaml
from app import config

_k8s_map_cache = None
_clients_initialized = False
_core_v1 = None
_apps_v1 = None


def _load_service_map() -> dict:
    global _k8s_map_cache
    if _k8s_map_cache is None:
        with open(config.SERVICE_K8S_MAP_PATH) as f:
            _k8s_map_cache = yaml.safe_load(f) or {}
    return _k8s_map_cache


def _get_k8s_target(service: str) -> dict:
    mapping = _load_service_map()
    target = mapping.get(service)
    if not target:
        raise ValueError(
            f"No Kubernetes mapping found for service '{service}'. "
            f"Add it to data/service_k8s_map.yaml before remediating it."
        )
    return target


def _init_clients() -> None:
    """Lazily import and configure the kubernetes client. Only called when
    an action is actually about to run against a real cluster."""
    global _clients_initialized, _core_v1, _apps_v1
    if _clients_initialized:
        return

    from kubernetes import client, config as kube_config
    from kubernetes.config.config_exception import ConfigException

    try:
        if config.KUBECONFIG_PATH:
            kube_config.load_kube_config(config_file=str(config.KUBECONFIG_PATH))
        else:
            kube_config.load_kube_config()
    except ConfigException:
        # Falls back to in-cluster config if running as a pod with a
        # service account (typical for a real deployed remediation service)
        kube_config.load_incluster_config()

    _core_v1 = client.CoreV1Api()
    _apps_v1 = client.AppsV1Api()
    _clients_initialized = True


def restart_pod(service: str) -> str:
    """Deletes pods matching the service's label selector. The owning
    Deployment/ReplicaSet immediately recreates them - this is the standard
    safe way to 'restart' in Kubernetes (there's no restart verb for pods)."""
    target = _get_k8s_target(service)
    namespace, selector = target["namespace"], target["label_selector"]

    if config.KUBE_DRY_RUN:
        msg = f"[DRY-RUN] Would delete pods in ns='{namespace}' matching '{selector}'"
        print(msg)
        return msg

    _init_clients()
    pods = _core_v1.list_namespaced_pod(namespace=namespace, label_selector=selector)
    deleted = []
    for pod in pods.items:
        _core_v1.delete_namespaced_pod(name=pod.metadata.name, namespace=namespace)
        deleted.append(pod.metadata.name)

    msg = f"Deleted {len(deleted)} pod(s) in '{namespace}': {deleted}"
    print(msg)
    return msg


def scale_up(service: str, increment: int = 1) -> str:
    """Patches the Deployment's replica count up by `increment`."""
    target = _get_k8s_target(service)
    namespace, deployment_name = target["namespace"], target["deployment_name"]

    if config.KUBE_DRY_RUN:
        msg = f"[DRY-RUN] Would scale deployment '{deployment_name}' in ns='{namespace}' by +{increment}"
        print(msg)
        return msg

    _init_clients()
    deployment = _apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    current = deployment.spec.replicas or 1
    new_count = current + increment

    _apps_v1.patch_namespaced_deployment_scale(
        name=deployment_name,
        namespace=namespace,
        body={"spec": {"replicas": new_count}},
    )
    msg = f"Scaled '{deployment_name}' in '{namespace}' from {current} to {new_count} replicas"
    print(msg)
    return msg


def rollback_deploy(service: str) -> str:
    """Rolls back to the previous revision. Uses `kubectl rollout undo`
    rather than the raw API because reconstructing ReplicaSet revision
    history correctly via the Python client is significantly more complex
    and error-prone than shelling out to a well-tested kubectl command."""
    target = _get_k8s_target(service)
    namespace, deployment_name = target["namespace"], target["deployment_name"]

    cmd = ["kubectl", "rollout", "undo", f"deployment/{deployment_name}", "-n", namespace]

    if config.KUBE_DRY_RUN:
        msg = f"[DRY-RUN] Would run: {' '.join(cmd)}"
        print(msg)
        return msg

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"rollback failed: {result.stderr.strip()}")

    msg = f"Rolled back '{deployment_name}' in '{namespace}': {result.stdout.strip()}"
    print(msg)
    return msg


# Registry mapping runbook action names -> actual functions.
# app/core/remediation.py looks actions up here.
ACTIONS = {
    "restart_pod": restart_pod,
    "scale_up": scale_up,
    "rollback_deploy": rollback_deploy,
}