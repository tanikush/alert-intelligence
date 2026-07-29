"""
Dynamic service topology: instead of a hardcoded dictionary, this reads a
simple annotation from each Kubernetes Service object to learn which
services are "downstream" of which upstream/root service - so a new
service can be wired into correlation just by annotating it, no code
change or redeploy of this app required.

Annotate a Service like this to declare it's downstream of checkout-api:

    metadata:
      annotations:
        alert-intelligence.io/upstream: checkout-api

The topology is rebuilt from the live cluster on a TTL (see
config.TOPOLOGY_CACHE_TTL_SECONDS) so newly annotated services are picked
up automatically, without restarting this app.

If the Kubernetes client can't reach a cluster (e.g. running locally on a
dev machine with no kubeconfig), this falls back to a small static map so
the app - and its tests - keep working without a live cluster.
"""

import time
import logging
from app import config

logger = logging.getLogger(__name__)

_ANNOTATION_KEY = "alert-intelligence.io/upstream"

# Fallback used when dynamic discovery is off, or the cluster is
# unreachable - keeps local dev and unit tests working without a real
# Kubernetes cluster.
STATIC_FALLBACK_TOPOLOGY = {
    "payments-service": "checkout-api",
    "fraud-detector": "payments-service",
}

_cache: dict[str, str] = {}
_cache_loaded_at: float = 0.0


def _load_k8s_client():
    """Tries in-cluster config first (when running as a pod), then falls
    back to the local kubeconfig (when running on a dev machine)."""
    from kubernetes import client, config as k8s_config
    from kubernetes.config.config_exception import ConfigException

    try:
        k8s_config.load_incluster_config()
    except ConfigException:
        k8s_config.load_kube_config(config_file=config.KUBECONFIG_PATH)
    return client.CoreV1Api()


def _fetch_topology_from_cluster() -> dict[str, str]:
    """Returns {downstream_service: upstream_root_service} built from the
    alert-intelligence.io/upstream annotation on Service objects in the
    configured namespace. Returns {} on any failure - callers merge this
    with the static fallback, so a cluster hiccup never breaks correlation."""
    topology = {}
    try:
        v1 = _load_k8s_client()
        services = v1.list_namespaced_service(namespace=config.K8S_TOPOLOGY_NAMESPACE)
        for svc in services.items:
            annotations = svc.metadata.annotations or {}
            upstream = annotations.get(_ANNOTATION_KEY)
            if upstream:
                topology[svc.metadata.name] = upstream
    except Exception as e:
        logger.warning(f"Could not fetch dynamic topology from Kubernetes: {e}")
    return topology


def get_topology() -> dict[str, str]:
    """Returns the current {downstream: upstream} map. Refreshes from the
    cluster if the cache has expired and dynamic discovery is enabled;
    always includes the static fallback entries as a safety net, with
    live cluster annotations taking priority over them."""
    global _cache, _cache_loaded_at

    if not config.USE_DYNAMIC_TOPOLOGY:
        return dict(STATIC_FALLBACK_TOPOLOGY)

    now = time.time()
    if now - _cache_loaded_at > config.TOPOLOGY_CACHE_TTL_SECONDS:
        _cache = _fetch_topology_from_cluster()
        _cache_loaded_at = now

    return {**STATIC_FALLBACK_TOPOLOGY, **_cache}