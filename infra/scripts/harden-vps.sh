#!/usr/bin/env bash
# ============================================================================
# Hardening de VPS contra ataques DoS / fuerza bruta.
# Ejecutar UNA VEZ como root/sudo al provisionar el servidor.
# Idempotente: se puede volver a correr sin romper nada.
# ============================================================================
set -euo pipefail

echo "==> Instalando dependencias (ufw, fail2ban)..."
apt-get update -qq
apt-get install -y ufw fail2ban curl

echo "==> Configurando UFW: solo 22 (SSH), 80 (HTTP), 443 (HTTPS)..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
ufw status verbose

echo "==> Endureciendo SSH (solo llave publica, sin root remoto)..."
SSHD_CONFIG=/etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "$SSHD_CONFIG"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' "$SSHD_CONFIG"
sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$SSHD_CONFIG"
sed -i 's/^#\?MaxAuthTries.*/MaxAuthTries 3/' "$SSHD_CONFIG"
systemctl reload ssh || systemctl reload sshd

echo "==> Mitigacion de SYN flood a nivel de kernel..."
cat > /etc/sysctl.d/99-dos-hardening.conf <<'EOF'
# Mitigacion de SYN flood
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2
# Ignorar broadcast pings (mitiga smurf attacks)
net.ipv4.icmp_echo_ignore_broadcasts = 1
# Ignorar paquetes ICMP con source route
net.ipv4.conf.all.accept_source_route = 0
# Descartar paquetes con IP origen invalida (spoofing)
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
# Limitar respuestas ICMP para evitar amplification
net.ipv4.icmp_ratelimit = 100
EOF
sysctl -p /etc/sysctl.d/99-dos-hardening.conf

echo "==> Habilitando y arrancando fail2ban..."
systemctl enable fail2ban
systemctl restart fail2ban

echo "==> Listo. Revisa 'ufw status' y 'fail2ban-client status' para confirmar."
