#!/usr/bin/env bash
set -euo pipefail
# Non-destructive by default. Production public DNS cutover is intentionally out of scope.
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
MODE="${1:---render}"
NAMESPACE="${SITE_ALBAN_K8S_NAMESPACE:-nabla-site-alban}"
HOST="${SITE_ALBAN_K8S_HOST:-alban-site.int.albandrieu.com}"
IMAGE="${SITE_ALBAN_K8S_IMAGE:-}"
INGRESS_CLASS="${SITE_ALBAN_K8S_INGRESS_CLASS:-traefik}"
DEPLOY_NAME=nabla-site-alban
MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT
case "$MODE" in --render|--preflight|--server-dry-run|--apply) ;; *) echo "Usage: $0 [--render|--preflight|--server-dry-run|--apply]" >&2; exit 2;; esac
if [[ "$MODE" != "--preflight" ]]; then
  [[ "$IMAGE" =~ @sha256:[a-f0-9]{64}$ ]] || {
    echo "SITE_ALBAN_K8S_IMAGE must be pinned to an immutable sha256 digest" >&2
    exit 1
  }
fi
[[ "$NAMESPACE" =~ ^[a-z0-9-]+$ && "$HOST" =~ ^[a-z0-9.-]+$ && "$INGRESS_CLASS" =~ ^[a-z0-9-]+$ ]] || exit 2
if [[ "$MODE" == "--preflight" || "$MODE" == "--server-dry-run" || "$MODE" == "--apply" ]]; then
  command -v kubectl >/dev/null
  kubectl get ingressclass "$INGRESS_CLASS" >/dev/null
  # Refuse any hostname already assigned to another ingress.
  command -v jq >/dev/null
  claims="$(kubectl get ingress -A -o json | jq -r --arg host "$HOST" --arg ns "$NAMESPACE" '.items[] | select(any(.spec.rules[]?; .host == $host)) | select(.metadata.namespace != $ns or .metadata.name != "nabla-site-alban") | "\\(.metadata.namespace)/\\(.metadata.name)"')"
  [[ -z "$claims" ]] || { echo "Ingress host already claimed: $claims" >&2; exit 1; }
fi
[[ "$MODE" == "--preflight" ]] && { echo "Ingress preflight passed"; exit 0; }
cat > "$MANIFEST" <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: $NAMESPACE
  labels:
    pod-security.kubernetes.io/enforce: restricted
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $DEPLOY_NAME
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels: {app: $DEPLOY_NAME}
  template:
    metadata:
      labels: {app: $DEPLOY_NAME}
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: website
          image: $IMAGE
          imagePullPolicy: IfNotPresent
          ports: [{name: http, containerPort: 3000}]
          readinessProbe:
            httpGet: {path: /fr, port: http}
            initialDelaySeconds: 10
            periodSeconds: 10
          resources:
            requests: {cpu: 100m, memory: 128Mi}
            limits: {cpu: "1", memory: 512Mi}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities: {drop: ["ALL"]}
            readOnlyRootFilesystem: true
---
apiVersion: v1
kind: Service
metadata:
  name: $DEPLOY_NAME
  namespace: $NAMESPACE
spec:
  selector: {app: $DEPLOY_NAME}
  ports: [{port: 80, targetPort: http}]
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: $DEPLOY_NAME
  namespace: $NAMESPACE
spec:
  ingressClassName: $INGRESS_CLASS
  rules:
    - host: $HOST
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: $DEPLOY_NAME
                port: {number: 80}
EOF
case "$MODE" in
  --render) cat "$MANIFEST";;
  --server-dry-run) kubectl apply --dry-run=server -f "$MANIFEST";;
  --apply)
    [[ "${SITE_ALBAN_K8S_ALLOW_APPLY:-false}" == true ]] || { echo "Set SITE_ALBAN_K8S_ALLOW_APPLY=true after review" >&2; exit 1; }
    kubectl apply -f "$MANIFEST"
    kubectl rollout status -n "$NAMESPACE" deployment/"$DEPLOY_NAME" --timeout=120s
    ;;
esac
