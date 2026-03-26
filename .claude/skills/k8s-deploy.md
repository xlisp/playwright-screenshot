---
name: k8s-deploy
description: Build Docker image and deploy the Playwright Screenshot service to Kubernetes
user_invocable: true
---

# Kubernetes Deployment Skill

Build and deploy the Playwright Screenshot API + Nginx reverse proxy to a Kubernetes cluster.

## Prerequisites

- `docker` and `kubectl` installed
- Kubernetes cluster accessible (`kubectl cluster-info` succeeds)
- For Vault methods: HashiCorp Vault server configured

## One-Command Deployment

```bash
# Default: Vault Agent Injector
./k8s/deploy.sh

# With custom registry and tag
./k8s/deploy.sh myregistry.com/repo v1.2.0

# Choose secret backend
./k8s/deploy.sh --vault-method=agent    # Vault Agent Injector (default)
./k8s/deploy.sh --vault-method=csi      # Vault CSI Provider
./k8s/deploy.sh --vault-method=secret   # Plain K8s Secret (no Vault)
```

## What deploy.sh Does

1. Checks prerequisites (docker, kubectl, cluster reachable)
2. Builds Docker image from project root
3. Pushes image to registry (if registry provided)
4. Creates namespace `playwright-screenshot`
5. Applies ConfigMap, Service, Archive PVC (20Gi RWX)
6. Creates ServiceAccount for Vault
7. Deploys API pods (chosen Vault method)
8. Deploys Nginx reverse proxy + LoadBalancer
9. Waits for rollout completion
10. Shows pod/pvc/svc status + usage examples

## Three Vault Methods

| Method | Flag | Use Case | Sidecar |
|--------|------|----------|---------|
| Agent Injector | `--vault-method=agent` | Production, existing Vault | Yes |
| CSI Provider | `--vault-method=csi` | Production, no sidecar | No |
| K8s Secret | `--vault-method=secret` | Dev/test, no Vault | No |

## Manual Deployment Steps

If you need to apply resources individually:

```bash
cd k8s/

# 1. Namespace + core
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f service.yaml
kubectl apply -f archive-pvc.yaml
kubectl apply -f vault-serviceaccount.yaml

# 2. API deployment (pick one)
kubectl apply -f deployment.yaml              # Vault Agent
kubectl apply -f vault-csi.yaml               # Vault CSI
kubectl apply -f github-secret.yaml && \
kubectl apply -f deployment-k8s-secret.yaml   # K8s Secret

# 3. Nginx
kubectl apply -f nginx-configmap.yaml
kubectl apply -f nginx-deployment.yaml
kubectl apply -f nginx-service.yaml
```

## Vault Server Setup (one-time)

```bash
export VAULT_ADDR=https://vault.example.com:8200
export VAULT_TOKEN=hvs.xxxxx
bash k8s/vault-setup.sh ghp_your_github_token
```

This script:
1. Enables KV v2 engine at `secret/`
2. Creates `playwright-screenshot` policy
3. Configures K8s auth method
4. Binds ServiceAccount to Vault role
5. Writes the GitHub token

## Verification After Deploy

```bash
# Port forward
kubectl -n playwright-screenshot port-forward svc/nginx 8080:80

# Health check
curl http://localhost:8080/health

# Vault status
curl http://localhost:8080/vault/status

# Test screenshot
curl -X POST http://localhost:8080/screenshot \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Test GitHub profile
curl http://localhost:8080/github/octocat/page
```

## Monitoring

```bash
# Pod status
kubectl -n playwright-screenshot get pods -o wide

# Logs
kubectl -n playwright-screenshot logs -f deploy/playwright-screenshot-api

# PVC usage
kubectl -n playwright-screenshot exec -it deploy/playwright-screenshot-api -- du -sh /app/archive/

# Nginx logs
kubectl -n playwright-screenshot logs -f deploy/nginx
```

## Cleanup

```bash
bash k8s/cleanup.sh
# or manually:
kubectl delete namespace playwright-screenshot
```

## Workflow

1. Ask the user which Vault method they want (default: agent).
2. Ask if they need a custom registry/tag.
3. Run `./k8s/deploy.sh` with the chosen options.
4. Verify with health check after deploy.
5. Show port-forward command for local access.
