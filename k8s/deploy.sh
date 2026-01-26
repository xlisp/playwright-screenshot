#!/bin/bash
#
# Playwright Screenshot K8s Deployment Script
# Deploys API service with Nginx reverse proxy
#
# Usage: ./deploy.sh [REGISTRY] [TAG]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
NAMESPACE="playwright-screenshot"

REGISTRY="${1:-}"
TAG="${2:-latest}"
IMAGE_NAME="playwright-screenshot"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        log_error "docker is not installed"
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
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
        log_info "Pushing image to registry..."
        docker push "$FULL_IMAGE"
        log_success "Image pushed: $FULL_IMAGE"
        
        log_info "Updating deployment YAML with image: $FULL_IMAGE"
        sed -i.bak "s|image: playwright-screenshot:latest|image: $FULL_IMAGE|g" "$SCRIPT_DIR/deployment.yaml"
        rm -f "$SCRIPT_DIR"/*.bak
    fi
}

deploy_k8s() {
    log_info "Deploying to Kubernetes..."
    
    log_info "Creating namespace..."
    kubectl apply -f "$SCRIPT_DIR/namespace.yaml"
    
    log_info "Creating ConfigMap..."
    kubectl apply -f "$SCRIPT_DIR/configmap.yaml"
    
    log_info "Creating PersistentVolumeClaim..."
    kubectl apply -f "$SCRIPT_DIR/pvc.yaml"
    
    log_info "Creating API Service..."
    kubectl apply -f "$SCRIPT_DIR/service.yaml"
    
    log_info "Creating API Deployment..."
    kubectl apply -f "$SCRIPT_DIR/deployment.yaml"
    
    log_info "Creating Nginx ConfigMap..."
    kubectl apply -f "$SCRIPT_DIR/nginx-configmap.yaml"
    
    log_info "Creating Nginx Deployment..."
    kubectl apply -f "$SCRIPT_DIR/nginx-deployment.yaml"
    
    log_info "Creating Nginx Service..."
    kubectl apply -f "$SCRIPT_DIR/nginx-service.yaml"
    
    log_success "Deployment completed"
}

wait_for_deployment() {
    log_info "Waiting for deployments to be ready..."
    
    kubectl -n "$NAMESPACE" rollout status deployment/playwright-screenshot-api --timeout=300s
    kubectl -n "$NAMESPACE" rollout status deployment/nginx --timeout=120s
    
    log_success "All deployments are ready"
}

show_status() {
    echo ""
    log_info "Deployment Status:"
    echo "===================="
    
    echo ""
    echo "Pods:"
    kubectl -n "$NAMESPACE" get pods -o wide
    
    echo ""
    echo "Services:"
    kubectl -n "$NAMESPACE" get svc
    
    echo ""
    echo "Deployments:"
    kubectl -n "$NAMESPACE" get deployment
    
    # Get external IP if LoadBalancer is ready
    echo ""
    EXTERNAL_IP=$(kubectl -n "$NAMESPACE" get svc nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    NODE_PORT=$(kubectl -n "$NAMESPACE" get svc nginx-nodeport -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "30080")
    
    if [ -n "$EXTERNAL_IP" ]; then
        echo "External IP: $EXTERNAL_IP"
        echo "API Endpoint: http://$EXTERNAL_IP/screenshot"
    else
        echo "LoadBalancer IP pending... Use NodePort for now:"
        echo "API Endpoint: http://<node-ip>:$NODE_PORT/screenshot"
    fi
}

show_usage() {
    echo ""
    log_info "API Usage Examples:"
    echo "===================="
    echo ""
    echo "1. Take a screenshot:"
    echo '   curl -X POST http://<IP>/screenshot \'
    echo '     -H "Content-Type: application/json" \'
    echo '     -d '"'"'{"url": "https://example.com"}'"'"
    echo ""
    echo "2. Take screenshot with options:"
    echo '   curl -X POST http://<IP>/screenshot \'
    echo '     -H "Content-Type: application/json" \'
    echo '     -d '"'"'{"url": "https://github.com", "width": 1280, "height": 720, "full_page": false}'"'"
    echo ""
    echo "3. List screenshots:"
    echo '   curl http://<IP>/screenshots'
    echo ""
    echo "4. Download a screenshot:"
    echo '   curl -O http://<IP>/screenshots/<filename>'
    echo ""
    echo "5. Health check:"
    echo '   curl http://<IP>/health'
    echo ""
    echo "6. Port-forward for local testing:"
    echo "   kubectl -n $NAMESPACE port-forward svc/nginx 8080:80"
    echo "   curl -X POST http://localhost:8080/screenshot -H 'Content-Type: application/json' -d '{\"url\": \"https://example.com\"}'"
    echo ""
}

main() {
    echo "========================================"
    echo "  Playwright Screenshot K8s Deployer"
    echo "  (API + Nginx)"
    echo "========================================"
    echo ""
    
    check_prerequisites
    build_image
    deploy_k8s
    wait_for_deployment
    show_status
    show_usage
    
    log_success "Deployment completed successfully!"
}

main "$@"
