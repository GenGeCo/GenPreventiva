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

---

## Account Utente App (Login Web)

| Campo | Valore |
|-------|--------|
| Email | `edilkit@gmail.com` |
| Username | `gruppogeas` |
| Password | `Test1234` |

---

## Chiave SSH Privata

Salva in un file (es. `~/.ssh/genpreventiva_key`) con `chmod 600`:

```
-----BEGIN OPENSSH PRIVATE KEY-----
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
-----END OPENSSH PRIVATE KEY-----
```

### Uso chiave da altro PC

```bash
# 1. Salva la chiave in un file
nano ~/.ssh/genpreventiva_key   # incolla contenuto

# 2. Imposta permessi
chmod 600 ~/.ssh/genpreventiva_key

# 3. Connettiti
ssh -i ~/.ssh/genpreventiva_key root@77.42.35.68
```

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
