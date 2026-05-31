# Step 0 — Docker on WSL2 (F10 verification harness prereq)

The verification harness runs in Docker. This box doesn't have Docker yet. Install **Docker Engine
inside WSL2** (no Docker Desktop needed). Run these yourself (they need `sudo`); in Claude Code you
can prefix a line with `!` to run it in the session.

This repo already uses `systemd --user` for the daemon, so WSL systemd is enabled
(`/etc/wsl.conf` → `[boot] systemd=true`) and `systemctl` works.

```bash
# 1) Docker apt repo + GPG key (Ubuntu/Debian WSL)
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 2) Install engine + compose plugin + buildx
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3) Run docker without sudo (re-login or `newgrp docker` after)
sudo usermod -aG docker "$USER"

# 4) Start + enable the daemon (systemd is on in this WSL)
sudo systemctl enable --now docker

# 5) Verify
docker run --rm hello-world
docker compose version
```

If `apt` is not Ubuntu/Debian, use the matching distro path from
https://docs.docker.com/engine/install/ . If you prefer Docker Desktop, just enable its WSL
integration for this distro instead of steps 1–4.

Once `docker run --rm hello-world` and `docker compose version` succeed, F10 Step 0 is done —
continue with `Dockerfile.verify` / `docker-compose.verify.yml` / `scripts/verify.sh`.
