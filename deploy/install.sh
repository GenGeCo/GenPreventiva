#!/bin/bash
# GenPreventiva - Script di installazione
# Eseguire come root sul server Hetzner

set -e

echo "=== GenPreventiva Installation Script ==="

# Variabili
APP_USER="genpreventiva"
APP_DIR="/opt/genpreventiva"
PYTHON_VERSION="3.12"

# 1. Crea utente se non esiste
if ! id "$APP_USER" &>/dev/null; then
    echo "Creating user $APP_USER..."
    useradd -m -s /bin/bash $APP_USER
fi

# 2. Crea struttura cartelle
echo "Creating directory structure..."
mkdir -p $APP_DIR/{app,storage,chromadb,logs,venv}
mkdir -p $APP_DIR/storage/{drawings,learning,temp}

# 3. Crea virtual environment
echo "Creating Python virtual environment..."
python$PYTHON_VERSION -m venv $APP_DIR/venv

# 4. Copia i file dell'applicazione
echo "Copying application files..."
# (Assumi che i file siano già nella cartella corrente)
cp -r app/* $APP_DIR/app/
cp requirements.txt $APP_DIR/

# 5. Installa dipendenze
echo "Installing Python dependencies..."
$APP_DIR/venv/bin/pip install --upgrade pip
$APP_DIR/venv/bin/pip install -r $APP_DIR/requirements.txt

# 6. Copia file .env (se non esiste)
if [ ! -f "$APP_DIR/app/.env" ]; then
    echo "Creating .env file from example..."
    cp $APP_DIR/app/.env.example $APP_DIR/app/.env
    echo "IMPORTANTE: Modifica $APP_DIR/app/.env con la tua GEMINI_API_KEY!"
fi

# 7. Imposta permessi
echo "Setting permissions..."
chown -R $APP_USER:$APP_USER $APP_DIR
chmod 600 $APP_DIR/app/.env

# 8. Installa servizio systemd
echo "Installing systemd service..."
cp deploy/genpreventiva.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable genpreventiva

# 9. Configura Nginx
echo "Configuring Nginx..."
cp deploy/nginx-genpreventiva.conf /etc/nginx/sites-available/genpreventiva
ln -sf /etc/nginx/sites-available/genpreventiva /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# 10. Crea database PostgreSQL (se non esiste)
echo "Setting up PostgreSQL..."
sudo -u postgres psql -c "CREATE USER genpreventiva WITH PASSWORD 'kaheipuvMNjguLNZ9kLI0LZaUOBHNMBHp15ba6ha';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE genpreventiva_db OWNER genpreventiva;" 2>/dev/null || true

# 11. Avvia il servizio
echo "Starting GenPreventiva service..."
systemctl start genpreventiva
sleep 2
systemctl status genpreventiva --no-pager

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit /opt/genpreventiva/app/.env and add your GEMINI_API_KEY"
echo "2. Restart the service: sudo systemctl restart genpreventiva"
echo "3. Access the app at: http://77.42.35.68:8081"
echo ""
echo "Useful commands:"
echo "  - View logs: journalctl -u genpreventiva -f"
echo "  - Restart: sudo systemctl restart genpreventiva"
echo "  - Status: sudo systemctl status genpreventiva"
