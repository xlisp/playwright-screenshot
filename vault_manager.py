#!/usr/bin/env python3
"""
Vault Secret Manager for GitHub API Token
──────────────────────────────────────────
Supports 3 modes for Kubernetes environments:

1. Vault Agent Sidecar / CSI  → reads token from file injected into Pod
2. Vault API (hvac)           → direct KV v2 access via ServiceAccount JWT
3. K8s Secret / Env fallback  → GITHUB_TOKEN env var from k8s Secret

Priority: Vault File → Vault API (k8s auth) → Env Var → Local file
"""

import os
import json
import base64
import hashlib
import getpass
from pathlib import Path
from datetime import datetime

try:
    import hvac
    HVAC_AVAILABLE = True
except ImportError:
    HVAC_AVAILABLE = False


class VaultSecretManager:
    """
    Manages GitHub API tokens with HashiCorp Vault + Kubernetes integration.

    In K8s the recommended flow is:
      - Vault Agent Injector or Vault CSI Provider writes the secret to a
        file inside the Pod (e.g. /vault/secrets/github-token).
      - This class reads from that file first.
      - If the file is missing it falls back to the Vault API using the
        Kubernetes auth method (JWT from the projected ServiceAccount token).
    """

    # ── Defaults (overridable via env) ────────────────────────────────
    VAULT_SECRET_PATH   = "secret/data/playwright-screenshot/github"
    VAULT_K8S_AUTH_PATH = "kubernetes"          # Vault auth mount
    VAULT_K8S_ROLE      = "playwright-screenshot"  # Vault role name

    # Vault Agent / CSI injects the secret to this path
    VAULT_FILE_PATH = Path(
        os.environ.get("VAULT_SECRET_FILE", "/vault/secrets/github-token")
    )

    # K8s ServiceAccount JWT (auto-mounted or projected)
    K8S_SA_TOKEN_PATH = Path(
        os.environ.get("K8S_SA_TOKEN_PATH",
                        "/var/run/secrets/kubernetes.io/serviceaccount/token")
    )

    # Local fallback
    LOCAL_SECRET_DIR  = Path.home() / ".playwright-screenshot"
    LOCAL_SECRET_FILE = LOCAL_SECRET_DIR / "secrets.enc"

    def __init__(self, vault_addr=None, vault_token=None):
        self.vault_addr = vault_addr or os.environ.get(
            "VAULT_ADDR", "http://vault.vault.svc.cluster.local:8200"
        )
        self.vault_token = vault_token or os.environ.get("VAULT_TOKEN")
        self.vault_role  = os.environ.get("VAULT_K8S_ROLE", self.VAULT_K8S_ROLE)
        self.vault_client = None
        self._init_vault()

    # ══════════════════════════════════════════════════════════════════
    #  Vault Initialisation
    # ══════════════════════════════════════════════════════════════════

    def _init_vault(self):
        """
        Try to connect to Vault.
        1. If VAULT_TOKEN is set → use token auth.
        2. Else if K8s SA JWT exists → use Kubernetes auth method.
        """
        if not HVAC_AVAILABLE:
            print("ℹ️  hvac not installed – Vault API disabled. "
                  "Install with: pip install hvac")
            return

        try:
            self.vault_client = hvac.Client(url=self.vault_addr)

            # --- Token auth (dev / external) ---
            if self.vault_token:
                self.vault_client.token = self.vault_token
                if self.vault_client.is_authenticated():
                    print(f"✅ Vault connected (token auth): {self.vault_addr}")
                    return
                print("⚠️  VAULT_TOKEN invalid")

            # --- Kubernetes auth ---
            if self.K8S_SA_TOKEN_PATH.exists():
                jwt = self.K8S_SA_TOKEN_PATH.read_text().strip()
                resp = self.vault_client.auth.kubernetes.login(
                    role=self.vault_role,
                    jwt=jwt,
                    mount_point=os.environ.get(
                        "VAULT_K8S_AUTH_PATH", self.VAULT_K8S_AUTH_PATH
                    ),
                )
                self.vault_client.token = resp["auth"]["client_token"]
                print(f"✅ Vault connected (k8s auth, role={self.vault_role}): "
                      f"{self.vault_addr}")
                return

            print("⚠️  No Vault credentials available – API disabled")
            self.vault_client = None

        except Exception as e:
            print(f"⚠️  Vault init failed: {e}")
            self.vault_client = None

    # ══════════════════════════════════════════════════════════════════
    #  1. Vault Agent / CSI File
    # ══════════════════════════════════════════════════════════════════

    def _file_retrieve(self) -> str | None:
        """Read token from Vault Agent injected file."""
        try:
            if self.VAULT_FILE_PATH.exists():
                token = self.VAULT_FILE_PATH.read_text().strip()
                # Vault Agent can write JSON or plain text
                if token.startswith("{"):
                    data = json.loads(token)
                    token = data.get("github_token") or data.get("token", "")
                if token:
                    print(f"✅ Token from Vault file: {self.VAULT_FILE_PATH}")
                    return token
        except Exception as e:
            print(f"⚠️  Vault file read error: {e}")
        return None

    # ══════════════════════════════════════════════════════════════════
    #  2. Vault API (KV v2)
    # ══════════════════════════════════════════════════════════════════

    def _vault_store(self, token: str) -> bool:
        if not self.vault_client:
            return False
        try:
            self.vault_client.secrets.kv.v2.create_or_update_secret(
                path="playwright-screenshot/github",
                secret=dict(
                    github_token=token,
                    updated_at=datetime.now().isoformat(),
                    updated_by=os.environ.get("HOSTNAME", getpass.getuser()),
                ),
            )
            print("✅ Token stored in Vault KV")
            return True
        except Exception as e:
            print(f"❌ Vault KV store failed: {e}")
            return False

    def _vault_retrieve(self) -> str | None:
        if not self.vault_client:
            return None
        try:
            resp = self.vault_client.secrets.kv.v2.read_secret_version(
                path="playwright-screenshot/github"
            )
            token = resp["data"]["data"].get("github_token")
            if token:
                print("✅ Token from Vault KV API")
            return token
        except Exception:
            return None

    def _vault_delete(self) -> bool:
        if not self.vault_client:
            return False
        try:
            self.vault_client.secrets.kv.v2.delete_metadata_and_all_versions(
                path="playwright-screenshot/github"
            )
            print("✅ Token deleted from Vault KV")
            return True
        except Exception as e:
            print(f"❌ Vault KV delete failed: {e}")
            return False

    # ══════════════════════════════════════════════════════════════════
    #  3. Local Encrypted File (dev fallback)
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _derive_key() -> bytes:
        machine_id = f"{getpass.getuser()}@{os.uname().nodename}"
        return hashlib.sha256(machine_id.encode()).digest()

    def _local_store(self, token: str) -> bool:
        try:
            self.LOCAL_SECRET_DIR.mkdir(parents=True, exist_ok=True)
            key = self._derive_key()
            data = json.dumps({
                "github_token": token,
                "updated_at": datetime.now().isoformat(),
            }).encode()
            encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
            self.LOCAL_SECRET_FILE.write_bytes(base64.b64encode(encrypted))
            self.LOCAL_SECRET_FILE.chmod(0o600)
            print(f"✅ Token stored locally: {self.LOCAL_SECRET_FILE}")
            return True
        except Exception as e:
            print(f"❌ Local store failed: {e}")
            return False

    def _local_retrieve(self) -> str | None:
        try:
            if not self.LOCAL_SECRET_FILE.exists():
                return None
            key = self._derive_key()
            encrypted = base64.b64decode(self.LOCAL_SECRET_FILE.read_bytes())
            data = bytes(b ^ key[i % len(key)] for i, b in enumerate(encrypted))
            secrets = json.loads(data.decode())
            token = secrets.get("github_token")
            if token:
                print("✅ Token from local file")
            return token
        except Exception:
            return None

    def _local_delete(self) -> bool:
        try:
            if self.LOCAL_SECRET_FILE.exists():
                self.LOCAL_SECRET_FILE.unlink()
                print("✅ Local secret file deleted")
            return True
        except Exception as e:
            print(f"❌ Local delete failed: {e}")
            return False

    # ══════════════════════════════════════════════════════════════════
    #  Public API
    # ══════════════════════════════════════════════════════════════════

    def store_github_token(self, token: str) -> bool:
        """Store token. Vault KV → local file."""
        if not token or not token.strip():
            print("❌ Token cannot be empty")
            return False
        if self._vault_store(token):
            return True
        return self._local_store(token)

    def get_github_token(self) -> str | None:
        """
        Retrieve token with priority:
          1. Vault Agent file  (/vault/secrets/github-token)
          2. Vault KV API      (k8s auth or token auth)
          3. Env var           (GITHUB_TOKEN from K8s Secret)
          4. Local file        (~/.playwright-screenshot/secrets.enc)
        """
        # 1️⃣ Vault Agent / CSI injected file
        token = self._file_retrieve()
        if token:
            return token

        # 2️⃣ Vault API
        token = self._vault_retrieve()
        if token:
            return token

        # 3️⃣ Environment variable (K8s Secret → env)
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            print("✅ Token from GITHUB_TOKEN env var")
            return token

        # 4️⃣ Local file
        return self._local_retrieve()

    def delete_github_token(self) -> bool:
        v = self._vault_delete()
        l = self._local_delete()
        return v or l

    def get_status(self) -> dict:
        """Full status of all secret backends."""
        vault_authed = False
        if self.vault_client:
            try:
                vault_authed = self.vault_client.is_authenticated()
            except Exception:
                pass

        return {
            "vault": {
                "hvac_installed": HVAC_AVAILABLE,
                "connected": vault_authed,
                "address": self.vault_addr,
                "k8s_role": self.vault_role,
                "k8s_sa_token_exists": self.K8S_SA_TOKEN_PATH.exists(),
            },
            "vault_file": {
                "path": str(self.VAULT_FILE_PATH),
                "exists": self.VAULT_FILE_PATH.exists(),
            },
            "environment": {
                "GITHUB_TOKEN": "set" if os.environ.get("GITHUB_TOKEN") else "not set",
                "VAULT_ADDR": os.environ.get("VAULT_ADDR", "not set"),
                "VAULT_TOKEN": "set" if os.environ.get("VAULT_TOKEN") else "not set",
            },
            "local_file": {
                "path": str(self.LOCAL_SECRET_FILE),
                "exists": self.LOCAL_SECRET_FILE.exists(),
            },
            "token_available": self.get_github_token() is not None,
        }


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vault Secret Manager")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="Show all backend status")
    sp = sub.add_parser("store", help="Store a GitHub token")
    sp.add_argument("token", nargs="?")
    sub.add_parser("get", help="Retrieve token")
    sub.add_parser("delete", help="Delete token")

    args = parser.parse_args()
    mgr = VaultSecretManager()

    if args.command == "status":
        import pprint; pprint.pprint(mgr.get_status())
    elif args.command == "store":
        t = args.token or getpass.getpass("GitHub Token: ")
        mgr.store_github_token(t)
    elif args.command == "get":
        t = mgr.get_github_token()
        if t:
            print(f"Token: {t[:4]}{'•' * (len(t) - 8)}{t[-4:]}")
        else:
            print("No token found")
    elif args.command == "delete":
        mgr.delete_github_token()
    else:
        parser.print_help()
