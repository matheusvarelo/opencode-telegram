#!/bin/bash
set -e

echo "🤖 Reiniciando OpenCode Telegram Bot..."
echo ""

# Check if service exists
if [ ! -f /etc/systemd/system/opencode-telegram.service ]; then
    echo "⚠️  Service file não encontrado. Copiando..."
    sudo cp /home/matheus/projetos/opencode-telegram/systemd/opencode-telegram.service /etc/systemd/system/
    sudo systemctl daemon-reload
fi

echo "📊 Status atual:"
sudo systemctl status opencode-telegram.service --no-pager || true
echo ""

echo "🔄 Reiniciando..."
sudo systemctl restart opencode-telegram.service
sleep 3

echo "✅ Bot reiniciado!"
echo ""
echo "📊 Novo status:"
sudo systemctl status opencode-telegram.service --no-pager

echo ""
echo "📜 Para ver logs em tempo real:"
echo "   sudo journalctl -u opencode-telegram.service -f"
echo ""
echo "🛑 Para parar o bot:"
echo "   sudo systemctl stop opencode-telegram.service"
