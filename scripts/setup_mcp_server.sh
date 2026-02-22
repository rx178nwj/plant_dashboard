#!/bin/bash
# =============================================================================
# Plant Monitor MCP Server セットアップスクリプト
#
# 概要:
#   SQLite DBをMCP経由で外部公開するサービスを設定します。
#   - plant-mcp.service       : mcpo REST APIサーバー (port 8765)
#   - plant-mcp-proxy.service : mcp-proxy SSEサーバー (port 8766, Claude Desktop用)
#
# 使い方:
#   sudo bash setup_mcp_server.sh
# =============================================================================

set -e

# ─────────────────────────────────────────────
# 設定値（必要に応じて変更）
# ─────────────────────────────────────────────
DB_PATH="/home/pi/plant_dashboard/data/plant_monitor.db"
SERVICE_USER="pi"
LOCAL_BIN="/home/pi/.local/bin"

MCPO_PORT=8765
MCPO_API_KEY="plant-monitor"

MCP_PROXY_PORT=8766

# ─────────────────────────────────────────────
# カラー出力
# ─────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERR]${NC}  $1"; exit 1; }

# ─────────────────────────────────────────────
# 前提チェック
# ─────────────────────────────────────────────
check_prerequisites() {
    info "前提条件を確認しています..."

    if [ "$(id -u)" -ne 0 ]; then
        error "このスクリプトはsudoで実行してください: sudo bash $0"
    fi

    if [ ! -f "$DB_PATH" ]; then
        error "データベースが見つかりません: $DB_PATH"
    fi

    if ! command -v pip3 &>/dev/null; then
        error "pip3 が見つかりません。Python3をインストールしてください。"
    fi

    success "前提条件OK"
}

# ─────────────────────────────────────────────
# Pythonパッケージのインストール
# ─────────────────────────────────────────────
install_packages() {
    info "Pythonパッケージをインストールしています..."

    # mcp-server-sqlite
    if [ -f "${LOCAL_BIN}/mcp-server-sqlite" ]; then
        success "mcp-server-sqlite は既にインストール済み"
    else
        info "mcp-server-sqlite をインストール中..."
        sudo -u "${SERVICE_USER}" pip3 install --user mcp-server-sqlite
        success "mcp-server-sqlite インストール完了"
    fi

    # mcpo (REST APIプロキシ)
    if [ -f "${LOCAL_BIN}/mcpo" ]; then
        success "mcpo は既にインストール済み"
    else
        info "mcpo をインストール中..."
        sudo -u "${SERVICE_USER}" pip3 install --user mcpo
        success "mcpo インストール完了"
    fi

    # mcp-proxy (SSEプロキシ / Claude Desktop用)
    if [ -f "${LOCAL_BIN}/mcp-proxy" ]; then
        success "mcp-proxy は既にインストール済み"
    else
        info "mcp-proxy をインストール中..."
        sudo -u "${SERVICE_USER}" pip3 install --user mcp-proxy
        success "mcp-proxy インストール完了"
    fi
}

# ─────────────────────────────────────────────
# systemdサービスの作成
# ─────────────────────────────────────────────
create_services() {
    info "systemdサービスを作成しています..."

    # plant-mcp.service (mcpo REST API)
    cat > /etc/systemd/system/plant-mcp.service << EOF
[Unit]
Description=Plant Monitor MCP HTTP Server (mcpo)
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
ExecStart=${LOCAL_BIN}/mcpo \\
    --host 0.0.0.0 \\
    --port ${MCPO_PORT} \\
    --api-key ${MCPO_API_KEY} \\
    -- ${LOCAL_BIN}/mcp-server-sqlite \\
    --db-path ${DB_PATH}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    success "plant-mcp.service 作成完了"

    # plant-mcp-proxy.service (SSE / Claude Desktop用)
    cat > /etc/systemd/system/plant-mcp-proxy.service << EOF
[Unit]
Description=Plant Monitor MCP Proxy (SSE/HTTP)
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
ExecStart=${LOCAL_BIN}/mcp-proxy \\
    --host 0.0.0.0 \\
    --port ${MCP_PROXY_PORT} \\
    -- ${LOCAL_BIN}/mcp-server-sqlite \\
    --db-path ${DB_PATH}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    success "plant-mcp-proxy.service 作成完了"
}

# ─────────────────────────────────────────────
# サービスの有効化・起動
# ─────────────────────────────────────────────
start_services() {
    info "サービスをリロード・起動しています..."

    systemctl daemon-reload

    for svc in plant-mcp plant-mcp-proxy; do
        systemctl enable "${svc}"
        systemctl restart "${svc}"
        sleep 2

        if systemctl is-active --quiet "${svc}"; then
            success "${svc} が起動しました"
        else
            warn "${svc} の起動に失敗しました。ログを確認してください:"
            journalctl -u "${svc}" -n 10 --no-pager
        fi
    done
}

# ─────────────────────────────────────────────
# 接続確認
# ─────────────────────────────────────────────
verify_endpoints() {
    info "エンドポイントを確認しています..."

    # mcpo REST API
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${MCPO_API_KEY}" \
        "http://localhost:${MCPO_PORT}/list_tables" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        success "mcpo REST API (port ${MCPO_PORT}): OK"
    else
        warn "mcpo REST API (port ${MCPO_PORT}): HTTP ${HTTP_CODE}"
    fi

    # mcp-proxy SSE
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 \
        "http://localhost:${MCP_PROXY_PORT}/sse" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        success "mcp-proxy SSE (port ${MCP_PROXY_PORT}): OK"
    else
        warn "mcp-proxy SSE (port ${MCP_PROXY_PORT}): HTTP ${HTTP_CODE}"
    fi
}

# ─────────────────────────────────────────────
# 完了メッセージ
# ─────────────────────────────────────────────
print_summary() {
    HOST_IP=$(hostname -I | awk '{print $1}')
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  セットアップ完了${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "  [REST API (mcpo)]"
    echo "    URL     : http://${HOST_IP}:${MCPO_PORT}"
    echo "    API Key : ${MCPO_API_KEY}"
    echo "    例      : curl -H 'Authorization: Bearer ${MCPO_API_KEY}' \\"
    echo "              http://${HOST_IP}:${MCPO_PORT}/list_tables"
    echo ""
    echo "  [SSE (Claude Desktop用)]"
    echo "    SSE URL : http://${HOST_IP}:${MCP_PROXY_PORT}/sse"
    echo ""
    echo "  [Windows claude_desktop_config.json に追加する設定]"
    echo '  "mcpServers": {'
    echo '    "plant-monitor-db": {'
    echo '      "command": "npx",'
    echo '      "args": ["-y", "mcp-remote",'
    echo "             \"http://${HOST_IP}:${MCP_PROXY_PORT}/sse\","
    echo '             "--allow-http"]'
    echo '    }'
    echo '  }'
    echo ""
}

# ─────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BLUE}Plant Monitor MCP Server セットアップ${NC}"
    echo "========================================"
    echo ""

    check_prerequisites
    install_packages
    create_services
    start_services
    verify_endpoints
    print_summary
}

main
