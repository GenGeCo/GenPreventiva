# Deploy GenPreventiva (AI CNC Estimator)

Guida completa per il deploy sul server Hetzner.

## Informazioni Server

```
IP:         77.42.35.68
SSH:        ssh root@77.42.35.68
User:       genpreventiva
App Path:   /opt/genpreventiva/app/
URL:        http://77.42.35.68:8081
```

## Architettura

```
Internet → Nginx (8081) → Uvicorn (8000) → FastAPI → PostgreSQL/Redis/ChromaDB
                              ↓
                    http://77.42.35.68:8081
```

---

## METODO 1: Deploy da Locale (scp)

### Step 1: Upload dei file

```bash
# Upload intera cartella app
scp -r app/* root@77.42.35.68:/opt/genpreventiva/app/

# Oppure file singoli
scp main.py root@77.42.35.68:/opt/genpreventiva/app/
scp requirements.txt root@77.42.35.68:/opt/genpreventiva/app/
```

### Step 2: Connessione al server

```bash
ssh root@77.42.35.68
```

### Step 3: Installa dipendenze (prima volta o se cambiate)

```bash
cd /opt/genpreventiva/app
source /opt/genpreventiva/venv/bin/activate
pip install -r requirements.txt
```

### Step 4: Sistema permessi

```bash
chown -R genpreventiva:genpreventiva /opt/genpreventiva/
```

### Step 5: Avvia/Restart servizio

```bash
systemctl restart genpreventiva
systemctl status genpreventiva
```

### One-liner completo (upload + install + restart)

```bash
scp -r app/* root@77.42.35.68:/opt/genpreventiva/app/ && ssh root@77.42.35.68 "cd /opt/genpreventiva/app && source /opt/genpreventiva/venv/bin/activate && pip install -r requirements.txt && chown -R genpreventiva:genpreventiva /opt/genpreventiva/ && systemctl restart genpreventiva && systemctl status genpreventiva"
```

---

## METODO 2: Deploy da GitHub

### Prima configurazione (una volta sola)

```bash
ssh root@77.42.35.68
cd /opt/genpreventiva
git clone https://github.com/TUOUSERNAME/genpreventiva.git app
chown -R genpreventiva:genpreventiva /opt/genpreventiva/
```

### Aggiornamenti successivi

```bash
ssh root@77.42.35.68
cd /opt/genpreventiva/app
git pull origin main
source /opt/genpreventiva/venv/bin/activate
pip install -r requirements.txt
systemctl restart genpreventiva
```

### Script deploy automatico (da creare)

```bash
# Crea /opt/genpreventiva/deploy.sh
cat > /opt/genpreventiva/deploy.sh << 'EOF'
#!/bin/bash
set -e
echo "=== GenPreventiva Deploy $(date) ==="

cd /opt/genpreventiva/app
git pull origin main

source /opt/genpreventiva/venv/bin/activate
pip install -r requirements.txt

chown -R genpreventiva:genpreventiva /opt/genpreventiva/
systemctl restart genpreventiva

echo "=== Deploy completato! ==="
systemctl status genpreventiva
EOF

chmod +x /opt/genpreventiva/deploy.sh
```

---

## Comandi Utili

### Controllare stato servizio

```bash
ssh root@77.42.35.68 "systemctl status genpreventiva"
```

### Vedere log in tempo reale

```bash
# Log applicazione
ssh root@77.42.35.68 "journalctl -u genpreventiva -f"

# Oppure file log diretto
ssh root@77.42.35.68 "tail -f /opt/genpreventiva/logs/app.log"
ssh root@77.42.35.68 "tail -f /opt/genpreventiva/logs/error.log"
```

### Restart rapido

```bash
ssh root@77.42.35.68 "systemctl restart genpreventiva"
```

### Test manuale (per debug)

```bash
ssh root@77.42.35.68
cd /opt/genpreventiva/app
source /opt/genpreventiva/venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Verificare che l'app risponda

```bash
curl http://77.42.35.68:8081/
curl http://77.42.35.68:8081/docs  # Swagger UI FastAPI
```

---

## Struttura File Server

```
/opt/genpreventiva/
├── app/                   # Codice sorgente
│   ├── main.py           # Entry point FastAPI
│   ├── requirements.txt  # Dipendenze Python
│   ├── models/           # Modelli database
│   ├── routes/           # Endpoint API
│   └── services/         # Logica business (Gemini, ChromaDB)
├── storage/              # PDF caricati
├── chromadb/             # Vector database persistente
├── logs/                 # Log applicazione
│   ├── app.log
│   ├── error.log
│   ├── nginx_access.log
│   └── nginx_error.log
├── venv/                 # Python virtual environment
└── deploy.sh             # Script deploy (da creare)
```

---

## Configurazione Servizio Systemd

Il servizio è già configurato in `/etc/systemd/system/genpreventiva.service`:

```ini
[Unit]
Description=GenPreventiva - AI CNC Estimator
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=genpreventiva
Group=genpreventiva
WorkingDirectory=/opt/genpreventiva/app
Environment=PATH=/opt/genpreventiva/venv/bin:/usr/bin
ExecStart=/opt/genpreventiva/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
StandardOutput=append:/opt/genpreventiva/logs/app.log
StandardError=append:/opt/genpreventiva/logs/error.log

[Install]
WantedBy=multi-user.target
```

### Abilitare autostart

```bash
ssh root@77.42.35.68 "systemctl enable genpreventiva"
```

---

## File .env (da creare sul server)

Crea `/opt/genpreventiva/app/.env`:

```bash
ssh root@77.42.35.68 "cat > /opt/genpreventiva/app/.env << 'EOF'
# Database
DATABASE_URL=postgresql://genpreventiva:kaheipuvMNjguLNZ9kLI0LZaUOBHNMBHp15ba6ha@127.0.0.1:5432/genpreventiva_db

# Redis
REDIS_URL=redis://127.0.0.1:6379/1

# ChromaDB
CHROMADB_PATH=/opt/genpreventiva/chromadb

# Storage
STORAGE_PATH=/opt/genpreventiva/storage

# Security
SECRET_KEY=6CJwuDhHYxPf31mia3YeTCyJek9ZTezHdEVDMjRWVUo

# Google AI
GEMINI_API_KEY=<INSERIRE_CHIAVE>
EOF"
```

---

## Sincronizzazione con GitHub

### Primo push (repo nuovo)

```bash
cd /percorso/locale/genpreventiva
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/TUOUSERNAME/genpreventiva.git
git push -u origin main
```

### Push successivi

```bash
git add .
git commit -m "Descrizione modifiche"
git push origin main
```

### Push + Deploy in un comando

```bash
git push origin main && ssh root@77.42.35.68 "/opt/genpreventiva/deploy.sh"
```

---

## Troubleshooting

### Servizio non parte

```bash
# Controlla errori
ssh root@77.42.35.68 "journalctl -u genpreventiva -n 100"

# Prova manualmente
ssh root@77.42.35.68 "cd /opt/genpreventiva/app && source /opt/genpreventiva/venv/bin/activate && python -m uvicorn main:app --host 127.0.0.1 --port 8000"
```

### Errori import Python

```bash
# Verifica dipendenze installate
ssh root@77.42.35.68 "source /opt/genpreventiva/venv/bin/activate && pip list"

# Reinstalla dipendenze
ssh root@77.42.35.68 "source /opt/genpreventiva/venv/bin/activate && pip install -r /opt/genpreventiva/app/requirements.txt"
```

### Errori permessi

```bash
ssh root@77.42.35.68 "chown -R genpreventiva:genpreventiva /opt/genpreventiva/"
```

### ChromaDB non scrive

```bash
ssh root@77.42.35.68 "ls -la /opt/genpreventiva/chromadb/"
ssh root@77.42.35.68 "chown -R genpreventiva:genpreventiva /opt/genpreventiva/chromadb/"
```

### Nginx non risponde su 8081

```bash
ssh root@77.42.35.68 "nginx -t && systemctl reload nginx"
ssh root@77.42.35.68 "cat /etc/nginx/sites-enabled/genpreventiva"
```

---

## Credenziali Rapide

| Risorsa | Valore |
|---------|--------|
| SSH | `ssh root@77.42.35.68` |
| User Linux | `genpreventiva` |
| URL App | `http://77.42.35.68:8081` |
| Database | `genpreventiva_db` |
| DB User | `genpreventiva` |
| DB Pass | `kaheipuvMNjguLNZ9kLI0LZaUOBHNMBHp15ba6ha` |
| Redis DB | `1` |
| Secret | `6CJwuDhHYxPf31mia3YeTCyJek9ZTezHdEVDMjRWVUo` |

**File completo**: vedi `CREDENZIALI_GENPREVENTIVA.txt`

---

## Isolamento da GecoGreen

Questo progetto è completamente separato da GecoGreen:

| Aspetto | GecoGreen | GenPreventiva |
|---------|-----------|---------------|
| Cartella | `/opt/gecogreen/` | `/opt/genpreventiva/` |
| User Linux | root | genpreventiva |
| Porta esterna | 80/443 | 8081 |
| Porta app | 3000/8080 | 8000 |
| Database | gecogreen | genpreventiva_db |
| Redis DB | 0 | 1 |
| Servizio | gecogreen-* | genpreventiva |
