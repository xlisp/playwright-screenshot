#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# vault-setup.sh — Configure HashiCorp Vault for playwright-screenshot
# ═══════════════════════════════════════════════════════════════════════
#
# Prerequisites:
#   - vault CLI installed and VAULT_ADDR / VAULT_TOKEN set
#   - Vault unsealed and KV v2 engine enabled at "secret/"
#   - Kubernetes auth method enabled
#
# Usage:
#   export VAULT_ADDR=https://vault.example.com:8200
#   export VAULT_TOKEN=hvs.xxxxx
#   bash vault-setup.sh [--github-token ghp_xxxxx]
#
set -euo pipefail

NAMESPACE="playwright-screenshot"
SA_NAME="playwright-screenshot"
VAULT_K8S_ROLE="playwright-screenshot"
VAULT_POLICY_NAME="playwright-screenshot"
SECRET_PATH="secret/data/playwright-screenshot/github"
GITHUB_TOKEN="${1:---}"   # pass via arg or prompted later

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()     { echo -e "${RED}[ERR]${NC} $*"; }

# ── Sanity checks ────────────────────────────────────────────────────
command -v vault >/dev/null || { err "vault CLI not found"; exit 1; }
[ -n "${VAULT_ADDR:-}" ]   || { err "VAULT_ADDR not set"; exit 1; }
[ -n "${VAULT_TOKEN:-}" ]  || { err "VAULT_TOKEN not set"; exit 1; }

echo ""
echo "══════════════════════════════════════════════"
echo "  Vault Setup for playwright-screenshot"
echo "══════════════════════════════════════════════"
echo ""

# ── 1. Enable KV v2 if needed ────────────────────────────────────────
info "Checking KV v2 secrets engine..."
if vault secrets list -format=json | jq -e '."secret/"' >/dev/null 2>&1; then
    ok "secret/ engine already enabled"
else
    info "Enabling KV v2 at secret/..."
    vault secrets enable -path=secret kv-v2
    ok "KV v2 enabled"
fi

# ── 2. Write the Vault policy ────────────────────────────────────────
info "Writing policy: ${VAULT_POLICY_NAME}"
vault policy write "${VAULT_POLICY_NAME}" - <<'EOF'
# playwright-screenshot policy
# Read-only access to the GitHub token secret
path "secret/data/playwright-screenshot/*" {
  capabilities = ["read", "list"]
}

# Allow the app to check its own token
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF
ok "Policy written"

# ── 3. Enable & configure Kubernetes auth ─────────────────────────────
info "Checking Kubernetes auth method..."
if vault auth list -format=json | jq -e '."kubernetes/"' >/dev/null 2>&1; then
    ok "kubernetes/ auth already enabled"
else
    info "Enabling Kubernetes auth..."
    vault auth enable kubernetes
    ok "Kubernetes auth enabled"
fi

# Configure K8s auth — reads the in-cluster config if Vault runs in K8s,
# or you can set K8S_HOST explicitly.
K8S_HOST="${K8S_HOST:-$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')}"
K8S_CA_CERT="${K8S_CA_CERT:-$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 -d)}"

info "Configuring Kubernetes auth (host: ${K8S_HOST})..."
vault write auth/kubernetes/config \
    kubernetes_host="${K8S_HOST}" \
    kubernetes_ca_cert="${K8S_CA_CERT}" \
    disable_local_ca_jwt=true
ok "Kubernetes auth configured"

# ── 4. Create the Vault role ──────────────────────────────────────────
info "Creating Vault role: ${VAULT_K8S_ROLE}"
vault write "auth/kubernetes/role/${VAULT_K8S_ROLE}" \
    bound_service_account_names="${SA_NAME}" \
    bound_service_account_namespaces="${NAMESPACE}" \
    policies="${VAULT_POLICY_NAME}" \
    ttl=1h \
    max_ttl=24h
ok "Role created (SA=${SA_NAME}, NS=${NAMESPACE})"

# ── 5. Store the GitHub token ─────────────────────────────────────────
if [ "${GITHUB_TOKEN}" = "---" ]; then
    echo ""
    read -rsp "Enter GitHub token (ghp_...): " GITHUB_TOKEN
    echo ""
fi

if [ -n "${GITHUB_TOKEN}" ] && [ "${GITHUB_TOKEN}" != "---" ]; then
    info "Storing GitHub token in Vault..."
    vault kv put secret/playwright-screenshot/github \
        github_token="${GITHUB_TOKEN}" \
        updated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        updated_by="vault-setup.sh"
    ok "Token stored at: secret/playwright-screenshot/github"
else
    warn "No token provided — skipping secret write"
fi

# ── 6. Verify ─────────────────────────────────────────────────────────
echo ""
info "Verification:"
echo "  Policy:  vault policy read ${VAULT_POLICY_NAME}"
echo "  Role:    vault read auth/kubernetes/role/${VAULT_K8S_ROLE}"
echo "  Secret:  vault kv get secret/playwright-screenshot/github"
echo ""

info "Testing read..."
vault kv get -format=json secret/playwright-screenshot/github | jq '.data.data | keys'

echo ""
ok "Vault setup complete! 🎉"
echo ""
echo "Next steps:"
echo "  1. kubectl apply -f k8s/vault-serviceaccount.yaml"
echo "  2. kubectl apply -f k8s/deployment.yaml   (uses Vault Agent annotations)"
echo "  3. Or kubectl apply -f k8s/vault-csi.yaml  (uses Vault CSI provider)"
echo ""
