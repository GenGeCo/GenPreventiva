# GenPreventiva - AI CNC Estimator

Sistema di preventivazione automatica per lavorazioni CNC basato su intelligenza artificiale.

## Funzionalita

- **Analisi Disegni**: Carica disegni tecnici (PDF/immagini) e l'AI li analizza
- **Preventivi Automatici**: Genera preventivi basandosi su esempi passati (RAG)
- **Apprendimento**: Il sistema impara dai tuoi preventivi reali
- **Chat AI**: Interagisci con l'AI per domande tecniche
- **Storico**: Tutti i preventivi salvati in PostgreSQL

## Stack Tecnologico

- **Backend**: Python 3.12 + FastAPI
- **AI**: Google Gemini 1.5 Pro (vision + reasoning)
- **Vector DB**: ChromaDB (embeddings locali)
- **Database**: PostgreSQL (metadati e storico)
- **Frontend**: HTML + TailwindCSS + Alpine.js
- **Deploy**: Systemd + Nginx

## Struttura Progetto

```
GenPreventiva/
├── app/
│   ├── main.py              # FastAPI app principale
│   ├── config.py            # Configurazione
│   ├── models/              # Modelli SQLAlchemy
│   │   ├── database.py
│   │   ├── user.py
│   │   ├── drawing.py
│   │   ├── quote.py
│   │   └── learning_example.py
│   ├── services/            # Business logic
│   │   ├── auth_service.py
│   │   ├── chromadb_service.py
│   │   ├── gemini_service.py
│   │   └── pdf_service.py
│   ├── routes/              # API endpoints
│   │   ├── auth.py
│   │   ├── chat.py
│   │   ├── learning.py
│   │   └── quotes.py
│   ├── templates/           # HTML templates
│   └── static/              # CSS, JS, images
├── deploy/
│   ├── genpreventiva.service
│   ├── nginx-genpreventiva.conf
│   └── install.sh
├── requirements.txt
└── README.md
```

## Installazione

### 1. Prerequisiti sul Server

```bash
# Python 3.12
apt install python3.12 python3.12-venv

# PostgreSQL (gia installato)
# Nginx (gia installato)
```

### 2. Deploy Automatico

```bash
# Copia i file sul server
scp -r . root@77.42.35.68:/tmp/genpreventiva/

# Esegui lo script di installazione
ssh root@77.42.35.68
cd /tmp/genpreventiva
chmod +x deploy/install.sh
./deploy/install.sh
```

### 3. Configurazione API Key

```bash
# Modifica il file .env
nano /opt/genpreventiva/app/.env

# Aggiungi la tua chiave Gemini
GEMINI_API_KEY=your-api-key-here

# Riavvia
systemctl restart genpreventiva
```

## Utilizzo

### Accesso
- URL: `http://77.42.35.68:8081`
- Registra un nuovo account
- Accedi alla dashboard

### Flusso di Lavoro

1. **Insegnamento** (prima volta)
   - Vai su "Insegnamento"
   - Carica preventivi passati con costi reali
   - Piu esempi = stime piu precise (30+ per ottima precisione)

2. **Generare Preventivi**
   - Vai su "Chat AI"
   - Carica un nuovo disegno
   - Clicca "Genera Preventivo Completo"
   - Il sistema cerca disegni simili e genera una stima

3. **Feedback**
   - Dopo aver completato un lavoro, inserisci il costo reale
   - Converti il preventivo in esempio di apprendimento

## API Endpoints

### Auth
- `POST /api/auth/register` - Registrazione
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Profilo utente

### Learning
- `POST /api/learning/upload` - Carica esempio
- `GET /api/learning/examples` - Lista esempi
- `GET /api/learning/stats` - Statistiche

### Quotes
- `POST /api/quotes/generate` - Genera preventivo
- `GET /api/quotes/` - Lista preventivi
- `GET /api/quotes/{id}` - Dettaglio preventivo

### Chat
- `POST /api/chat/send` - Invia messaggio
- `POST /api/chat/send-with-file` - Messaggio con file

## Comandi Utili

```bash
# Status servizio
systemctl status genpreventiva

# Logs in tempo reale
journalctl -u genpreventiva -f

# Restart
systemctl restart genpreventiva

# Log applicazione
tail -f /opt/genpreventiva/logs/app.log
```

## Come Funziona il RAG

1. **Insegnamento**: Quando carichi un esempio:
   - Gemini analizza il disegno
   - Viene creato un embedding (vettore) della descrizione
   - Il vettore viene salvato in ChromaDB
   - I metadati vanno in PostgreSQL

2. **Preventivo**: Quando generi un preventivo:
   - Gemini analizza il nuovo disegno
   - ChromaDB cerca i 3 vettori piu simili
   - I dati degli esempi simili vengono recuperati
   - Gemini genera il preventivo basandosi sugli esempi

## Troubleshooting

### "GEMINI_API_KEY non configurata"
```bash
nano /opt/genpreventiva/app/.env
# Aggiungi: GEMINI_API_KEY=xxx
systemctl restart genpreventiva
```

### Errori di permessi
```bash
chown -R genpreventiva:genpreventiva /opt/genpreventiva
```

### Database non raggiungibile
```bash
systemctl status postgresql
sudo -u postgres psql -c "\l"  # Lista database
```

## Licenza

Progetto privato - Tutti i diritti riservati
