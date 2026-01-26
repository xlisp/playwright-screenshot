#!/bin/bash
#
# Playwright Screenshot K8s Deployment Script
# Usage: ./deploy.sh [REGISTRY] [TAG]
#
# Examples:
#   ./deploy.sh                           # Use local image
#   ./deploy.sh docker.io/myuser latest   # Push to Docker Hub
#   ./deploy.sh registry.example.com/repo v1.0.0
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
NAMESPACE="playwright-screenshot"

# Parse arguments
REGISTRY="${1:-}"
TAG="${2:-latest}"
IMAGE_NAME="playwright-screenshot"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
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
    
    # Check if kubectl can connect to cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Build Docker image
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
    
    # Push to registry if specified
    if [ -n "$REGISTRY" ]; then
        log_info "Pushing image to registry..."
        docker push "$FULL_IMAGE"
        log_success "Image pushed: $FULL_IMAGE"
    fi
    
    # Update deployment with new image
    if [ -n "$REGISTRY" ]; then
        log_info "Updating deployment YAML with image: $FULL_IMAGE"
        sed -i.bak "s|image: playwright-screenshot:latest|image: $FULL_IMAGE|g" "$SCRIPT_DIR/deployment.yaml"
        sed -i.bak "s|image: playwright-screenshot:latest|image: $FULL_IMAGE|g" "$SCRIPT_DIR/job.yaml"
        sed -i.bak "s|image: playwright-screenshot:latest|image: $FULL_IMAGE|g" "$SCRIPT_DIR/cronjob.yaml"
        rm -f "$SCRIPT_DIR"/*.bak
    fi
}

# Deploy to Kubernetes
deploy_k8s() {
    log_info "Deploying to Kubernetes..."
    
    # Apply resources in order
    log_info "Creating namespace..."
    kubectl apply -f "$SCRIPT_DIR/namespace.yaml"
    
    log_info "Creating ConfigMap..."
    kubectl apply -f "$SCRIPT_DIR/configmap.yaml"
    
    log_info "Creating PersistentVolumeClaim..."
    kubectl apply -f "$SCRIPT_DIR/pvc.yaml"
    
    log_info "Creating Deployment..."
    kubectl apply -f "$SCRIPT_DIR/deployment.yaml"
    
    log_success "Base deployment completed"
    
    # Ask about optional resources
    echo ""
    read -p "Deploy CronJob for scheduled screenshots? (y/N): " deploy_cronjob
    if [[ "$deploy_cronjob" =~ ^[Yy]$ ]]; then
        kubectl apply -f "$SCRIPT_DIR/cronjob.yaml"
        log_success "CronJob deployed"
    fi
}

# Wait for deployment to be ready
wait_for_deployment() {
    log_info "Waiting for deployment to be ready..."
    
    kubectl -n "$NAMESPACE" rollout status deployment/playwright-screenshot --timeout=300s
    
    log_success "Deployment is ready"
}

# Show status
show_status() {
    echo ""
    log_info "Deployment Status:"
    echo "===================="
    
    echo ""
    echo "Pods:"
    kubectl -n "$NAMESPACE" get pods
    
    echo ""
    echo "Deployment:"
    kubectl -n "$NAMESPACE" get deployment
    
    echo ""
    echo "PVC:"
    kubectl -n "$NAMESPACE" get pvc
    
    if kubectl -n "$NAMESPACE" get cronjob &> /dev/null 2>&1; then
        echo ""
        echo "CronJobs:"
        kubectl -n "$NAMESPACE" get cronjob
    fi
}

# Usage instructions
show_usage() {
    echo ""
    log_info "Usage Instructions:"
    echo "===================="
    echo ""
    echo "1. Run a one-time screenshot job:"
    echo "   kubectl -n $NAMESPACE create job screenshot-\$(date +%s) --from=job/screenshot-job"
    echo ""
    echo "2. Execute screenshot in running pod:"
    echo "   POD=\$(kubectl -n $NAMESPACE get pod -l app=playwright-screenshot -o jsonpath='{.items[0].metadata.name}')"
    echo "   kubectl -n $NAMESPACE exec -it \$POD -- /app/entrypoint.sh 'https://example.com' '/app/screenshots/test.png'"
    echo ""
    echo "3. Copy screenshots from pod:"
    echo "   kubectl -n $NAMESPACE cp \$POD:/app/screenshots/test.png ./test.png"
    echo ""
    echo "4. View logs:"
    echo "   kubectl -n $NAMESPACE logs -l app=playwright-screenshot"
    echo ""
    echo "5. Scale deployment:"
    echo "   kubectl -n $NAMESPACE scale deployment/playwright-screenshot --replicas=3"
    echo ""
}

# Main execution
main() {
    echo "========================================"
    echo "  Playwright Screenshot K8s Deployer"
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
