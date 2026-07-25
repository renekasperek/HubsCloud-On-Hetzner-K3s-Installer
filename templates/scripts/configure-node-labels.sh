#!/bin/bash
# Pin k3s ServiceLB (svclb) to the master node only.
# Without this, svclb binds 4443/5349 on the WebRTC worker and blocks dialog/coturn hostNetwork pods.
# The installer pipeline applies these labels automatically; use this script for manual recovery.

set -euo pipefail

MASTER_NODE=$(kubectl get nodes -l workload-type=database -o jsonpath='{.items[0].metadata.name}')
if [ -z "$MASTER_NODE" ]; then
  echo "Master node not found (need workload-type=database)"
  kubectl get nodes --show-labels
  exit 1
fi

echo "Labeling $MASTER_NODE for svclb pool master-only"
kubectl label nodes "$MASTER_NODE" svccontroller.k3s.cattle.io/enablelb=true --overwrite
kubectl label nodes "$MASTER_NODE" svccontroller.k3s.cattle.io/lbpool=master-only --overwrite

echo "Done. Delete stray svclb pods if any still run on WebRTC/web workers:"
echo "  kubectl get pods -A | grep svclb-haproxy-ingress-lb"
