#!/bin/bash
#
# Cleanup script - Remove all Playwright Screenshot K8s resources
# Usage: ./cleanup.sh
#

set -e

NAMESPACE="playwright-screenshot"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}WARNING: This will delete all Playwright Screenshot resources!${NC}"
echo ""
read -p "Are you sure you want to continue? (y/N): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Deleting resources..."

# Delete in reverse order
kubectl delete cronjob --all -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null || true
kubectl delete jobs --all -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null || true
kubectl delete deployment --all -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null || true
kubectl delete pvc --all -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null || true
kubectl delete configmap --all -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null || true
kubectl delete namespace "$NAMESPACE" --ignore-not-found=true 2>/dev/null || true

echo -e "${GREEN}Cleanup completed!${NC}"
