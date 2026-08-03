# WECADI - Prestige Event & Bar Management System

Applicazione web full-stack sviluppata in Python (Flask) per la gestione integrata di eventi di lusso. Il sistema copre l'intero ciclo di vita dell'evento: dalla prenotazione del biglietto e generazione del QR code, fino alla gestione in tempo reale delle ordinazioni al bar e del flusso di cassa tramite un sistema multi-ruolo.

## Tecnologie Utilizzate

* **Backend:** Python 3, Flask
* **Database & Cloud Services:** Supabase (PostgreSQL, Realtime API)
* **Frontend:** HTML5, CSS3, JavaScript (Jinja2 Templates)
* **Gestione Stato & Polling:** Polling asincrono lato client tramite JavaScript fetch API
* **Sicurezza:** Gestione sessioni Flask, chiavi segrete configurate (`wecadi_prestige_key_2026`)

## Funzionalità Principali e Architettura Multi-Ruolo

Il sistema è suddiviso in tre macro-aree con logiche di business isolate per garantire sicurezza e fluidità durante l'evento.

### 1. Portale Clienti (Dashboard Utente)

* **Prenotazione e Accesso:** Registrazione tramite Email e Telefono con generazione di un codice cliente univoco.
* **Live Status:** Visualizzazione in tempo reale dello stato del biglietto (`In attesa`, `Confirmé`, `Présent`) e del livello VIP (`Classique`, `Premium`, `VIP`).
* **Ordinazioni dal Tavolo:** Carrello dinamico con controllo istantaneo delle scorte di magazzino.
* **Motore di Pricing Avanzato:** Calcolo automatico di sconti e "bundle" (es. 3x Coca-Cola a prezzo ridotto) implementato direttamente nel dizionario `INVENTORY` del backend.

### 2. Portale Staff (Dashboard Operative)

Accesso protetto da password specifiche per ruolo per garantire la separazione dei compiti:

* **Barman:** Visualizza le code di preparazione (`À préparer`), aggiorna l'inventario in modo massivo (bulk update) e segna i drink come pronti per la consegna (`Prêt au bar`).
* **Serveuse (Cameriera):** Prende in carico gli ordini da incassare (`À encaisser`). Il sistema implementa un blocco di **concorrenza (Concurrency Control)** tramite query Supabase condizionali per impedire che due cameriere prendano in carico lo stesso ordine.
* **Caisse (Cassa/Supervisore):** Monitora il totale incassato da ogni singola cameriera e registra i versamenti parziali in contanti durante la serata per calcolare il debito residuo (`da_versare`).

### 3. Portale Amministratore (Admin Dashboard)

* **Validazione Ingressi:** Validazione delle prenotazioni con generazione automatica di un QR Code univoco in formato esadecimale.
* **Controllo Accessi:** Sistema di scansione manuale dei QR Code per l'ingresso, con blocco preventivo per biglietti già scansionati (`DÉJÀ ÉTÉ SCANNÉ`).
* **Gestione Utenti:** Modifica dei Tier (Classique/Premium/VIP), sospensione o eliminazione degli account.

## Dettagli Ingegneristici

* **Gestione del Polling e Connessioni:** Per evitare problemi di socket su ambienti Windows (es. `WinError 10035`), le route di polling (`/api/live_status` e `/api/staff/updates`) istanziano client Supabase locali e isolati, prevenendo la saturazione delle connessioni in background.
* **Gestione Inventario Live:** Sottrazione atomica delle scorte dal database al momento esatto della conferma dell'ordine per evitare l'over-selling.

## Guida all'Avvio Rapido (Sviluppo Locale)

L'applicazione è progettata per un avvio rapido senza complesse configurazioni di database locali, appoggiandosi completamente all'infrastruttura Cloud di Supabase.

**Passaggio 1: Clonare il repository**

```bash
git clone <inserire-url-del-repo>
cd wecadi

```

**Passaggio 2: Creare l'ambiente virtuale e installare le dipendenze**

```bash
python -m venv venv
source venv/bin/activate  # Su Windows: venv\Scripts\activate
pip install flask supabase

```

**Passaggio 3: Avviare il server Flask**

```bash
python app.py
# oppure
flask run --debug

```

L'applicazione sarà immediatamente disponibile all'indirizzo `http://localhost:5000`.
Le credenziali del database (URL e API Key di Supabase) sono attualmente integrate nel codice sorgente per consentire un test immediato dell'infrastruttura live.
