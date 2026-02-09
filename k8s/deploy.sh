#!/bin/bash
#
# Playwright Screenshot K8s Deployment Script
# Deploys API service with Nginx reverse proxy + Vault + Archive PVC
#
# Usage:
#   ./deploy.sh [REGISTRY] [TAG]
#   ./deploy.sh --vault-method=agent    # Vault Agent Injector (default)
#   ./deploy.sh --vault-method=csi      # Vault CSI Provider
#   ./deploy.sh --vault-method=secret   # Plain K8s Secret (no Vault)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
NAMESPACE="playwright-screenshot"

REGISTRY=""
TAG="latest"
IMAGE_NAME="playwright-screenshot"
VAULT_METHOD="agent"  # agent | csi | secret

for arg in "$@"; do
    case $arg in
        --vault-method=*) VAULT_METHOD="${arg#*=}"; shift ;;
        --*) shift ;;
        *)
            if [ -z "$REGISTRY" ]; then REGISTRY="$arg"
            elif [ "$TAG" = "latest" ]; then TAG="$arg"
            fi
            ;;
    esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERR]${NC} $1"; }

check_prerequisites() {
    log_info "Checking prerequisites..."
    command -v kubectl &>/dev/null || { log_error "kubectl not installed"; exit 1; }
    command -v docker  &>/dev/null || { log_error "docker not installed"; exit 1; }
    kubectl cluster-info &>/dev/null || { log_error "Cannot reach K8s cluster"; exit 1; }
    log_success "Prerequisites OK"
}

build_image() {
    log_info "Building Docker image..."
    cd "$PROJECT_DIR"
    if [ -n "$REGISTRY" ]; then
        FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"
    else
        FULL_IMAGE="${IMAGE_NAME}:${TAG}"
    fi
    docker build -t "$FULL_IMAGE" .
    log_success "Image built: $FULL_IMAGE"
    if [ -n "$REGISTRY" ]; then
        docker push "$FULL_IMAGE"
        log_success "Image pushed: $FULL_IMAGE"
    fi
}

deploy_k8s() {
    log_info "Deploying to Kubernetes (vault-method=${VAULT_METHOD})..."

    # Core resources
    kubectl apply -f "$SCRIPT_DIR/namespace.yaml"
    kubectl apply -f "$SCRIPT_DIR/configmap.yaml"
    kubectl apply -f "$SCRIPT_DIR/service.yaml"

    # ⭐ Archive PVC — persistent storage that survives redeploy
    log_info "Creating Archive PVC (persistent storage)..."
    kubectl apply -f "$SCRIPT_DIR/archive-pvc.yaml"

    # ServiceAccount
    kubectl apply -f "$SCRIPT_DIR/vault-serviceaccount.yaml"

    # Deployment — pick by vault method
    case "$VAULT_METHOD" in
        agent)
            log_info "Using Vault Agent Injector..."
            kubectl apply -f "$SCRIPT_DIR/deployment.yaml"
            ;;
        csi)
            log_info "Using Vault CSI Provider..."
            kubectl apply -f "$SCRIPT_DIR/vault-csi.yaml"
            ;;
        secret)
            log_info "Using plain K8s Secret (no Vault)..."
            kubectl apply -f "$SCRIPT_DIR/github-secret.yaml"
            kubectl apply -f "$SCRIPT_DIR/deployment-k8s-secret.yaml"
            ;;
        *)
            log_error "Unknown vault-method: ${VAULT_METHOD}"
            exit 1
            ;;
    esac

    # Nginx
    kubectl apply -f "$SCRIPT_DIR/nginx-configmap.yaml"
    kubectl apply -f "$SCRIPT_DIR/nginx-deployment.yaml"
    kubectl apply -f "$SCRIPT_DIR/nginx-service.yaml"

    log_success "K8s resources applied"
}

wait_for_deployment() {
    log_info "Waiting for rollout..."
    kubectl -n "$NAMESPACE" rollout status deployment/playwright-screenshot-api --timeout=300s 2>/dev/null || \
    kubectl -n "$NAMESPACE" rollout status deployment/playwright-screenshot-api-csi --timeout=300s 2>/dev/null || true
    kubectl -n "$NAMESPACE" rollout status deployment/nginx --timeout=120s 2>/dev/null || true
    log_success "Rollout complete"
}

show_status() {
    echo ""
    log_info "═══ Deployment Status ═══"
    echo ""
    echo "Vault Method: ${VAULT_METHOD}"
    echo ""
    echo "Pods:"
    kubectl -n "$NAMESPACE" get pods -o wide
    echo ""
    echo "PVCs:"
    kubectl -n "$NAMESPACE" get pvc
    echo ""
    echo "Services:"
    kubectl -n "$NAMESPACE" get svc
    echo ""
}

show_usage() {
    echo ""
    log_info "═══ API Usage ═══"
    echo ""
    echo "Port-forward:"
    echo "  kubectl -n $NAMESPACE port-forward svc/nginx 8080:80"
    echo ""
    echo "GitHub profile → archive:"
    echo "  curl http://localhost:8080/github/octocat/page           # HTML (auto-archived)"
    echo "  curl -X POST http://localhost:8080/github/octocat/screenshot  # HTML + PNG (archived)"
    echo ""
    echo "Browse archive (persistent, survives redeploy):"
    echo "  curl http://localhost:8080/archive                             # list users"
    echo "  curl http://localhost:8080/archive/octocat                     # list snapshots"
    echo "  curl http://localhost:8080/archive/octocat/latest/profile.html # latest HTML"
    echo "  curl http://localhost:8080/archive/octocat/latest/profile.png  # latest screenshot"
    echo ""
    echo "Debug archive PVC directly:"
    echo "  kubectl -n $NAMESPACE exec -it deploy/playwright-screenshot-api -- ls -la /app/archive/"
    echo ""
}

main() {
    echo "════════════════════════════════════════════"
    echo "  Playwright Screenshot K8s Deployer"
    echo "  Vault method: ${VAULT_METHOD}"
    echo "════════════════════════════════════════════"
    echo ""
    check_prerequisites
    build_image
    deploy_k8s
    wait_for_deployment
    show_status
    show_usage
    log_success "Done! 🎉"
}

main "$@"
