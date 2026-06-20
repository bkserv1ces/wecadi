import os
import secrets
import string
import json
import random
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase import create_client, Client


# Dizionario dei prezzi per calcolare il totale nel backend
INVENTORY = {
    # SOFT & EAU
    'eau': {'name': 'Eau', 'price': 1},
    'coca': {'name': 'Coca', 'price': 5, 'bundleQty': 3, 'bundlePrice': 10},
    'san_pellegrino': {'name': 'San Pellegrino', 'price': 5, 'bundleQty': 3, 'bundlePrice': 10},
    'redbull': {'name': 'Red Bull', 'price': 5},
    'malta': {'name': 'Malta Bouteille', 'price': 5},
    
    # VINS & CHAMPAGNES
    'fior_arancio': {'name': "Fior D'Arancio (dolce)", 'price': 30},
    'colli_eugani': {'name': 'Colli Eugani (dolce)', 'price': 30},
    'martini': {'name': 'Martini (dolce)', 'price': 30},
    'ca_de_mari': {'name': 'Ca De Mari (Prosecco)', 'price': 30},
    'colligny': {'name': 'Colligny (champagne)', 'price': 75},
    'moet': {'name': 'Moët Chandon', 'price': 100},
    'veuve': {'name': 'Veuve Clicquot', 'price': 100},
    'ruinart': {'name': 'Ruinart (sur réservation)', 'price': 150},
    
    # SPIRITUEUX
    'vecchia_romagna': {'name': 'Vecchia Romagna', 'price': 40},
    'bailey': {'name': 'Bailey', 'price': 50},
    'black_label': {'name': 'Black Label', 'price': 70},
    'gold_label': {'name': 'Gold Label', 'price': 100},
    'chivas_18': {'name': 'Chivas 18 ans', 'price': 120},
    
    # NOURRITURE
    'brochettes': {'name': 'Brochettes (gésier/bœuf)', 'price': 2},
    
    # --- ANCIENS PRODUITS (Pour compatibilità dei vecchi ordini nel database) ---
    'belaire': {'name': 'Luc Belaire (Ancien)', 'price': 80},
    'prosecco': {'name': 'Prosecco (Ancien)', 'price': 30},
    'spumante': {'name': 'Spumante (Ancien)', 'price': 30},
    'gold': {'name': 'Gold (Ancien)', 'price': 100},
    'jack_daniel': {'name': "Jack Daniel's (Ancien)", 'price': 70}
}


# Inizializzazione Supabase
url: str = "https://nujvctqiggtxyeewvexu.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im51anZjdHFpZ2d0eHllZXd2ZXh1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTI5OTE3NCwiZXhwIjoyMDk0ODc1MTc0fQ.nwJXQxvj8YNWjZnEoWd0len471k2sjJa2BlUfGxDk6U"
supabase: Client = create_client(url, key)

app = Flask(__name__)
app.secret_key = 'wecadi_prestige_key_2026'

# Imposta la durata della sessione a 90 giorni per ricordare l'utente
app.permanent_session_lifetime = timedelta(days=90)

# ---------------------------------------------------------
# CONFIGURAZIONE PASSWORD STAFF & ADMIN
# ---------------------------------------------------------
ADMIN_PASSWORD = 'w26-wecadi'

# Password specifiche per ogni ruolo dello Staff
STAFF_PASSWORDS = {
    'serveuse': 'coca-26',
    'barman': 'phone-26',
    'caisse': 'euro-26'
}


# ---------------------------------------------------------
# HELPER FUNCTIONS (Funzioni di utilità interna)
# ---------------------------------------------------------
def format_ordine_text(ordine_json):
    """Transforma il JSON dell'ordine in testo leggibile (es: '2x Coca, 1x Moet')"""
    dettagli = []
    for item_id, qty in ordine_json.items():
        if qty > 0 and item_id in INVENTORY:
            dettagli.append(f"{qty}x {INVENTORY[item_id]['name']}")
    return ", ".join(dettagli)


# ----------------- API TEMPS RÉEL (POLLING CLIENT) ----------------- #

@app.route('/api/live_status')
def api_live_status():
    if 'user_id' not in session:
        return jsonify({'error': 'Non autorisé'}), 401
    
    try:
        # Creazione di un client locale per isolare la connessione di background 
        # ed evitare collisioni di socket su Windows (WinError 10035)
        local_supabase = create_client(url, key)
        
        user_data = local_supabase.table("prenotazioni").select("stato, tier_bar").eq("id", session['user_id']).execute().data[0]
        
        # Recupera lo stato attuale di tutti gli ordini del cliente
        ordini = local_supabase.table("commandes_bar").select("id, stato").eq("prenotazione_id", session['user_id']).execute().data
        stati_ordini = {str(o['id']): o['stato'] for o in ordini}
        
        return jsonify({
            'stato': user_data.get('stato', 'In attesa'),
            'tier_bar': user_data.get('tier_bar', 'Classique'),
            'stati_ordini': stati_ordini
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

# ---------------------------------------------------------
# API TEMPS RÉEL STAFF (POLLING STAFF)
# ---------------------------------------------------------

@app.route('/api/staff/updates')
def api_staff_updates():
    if 'staff_role' not in session:
        return jsonify({'error': 'Non autorisé'}), 401
    
    role = session['staff_role']
    nome = session.get('staff_nome')
    
    try:
        # Creazione di un client locale per evitare WinError 10035 su Windows
        local_supabase = create_client(url, key)
        
        query = local_supabase.table("commandes_bar").select("*").neq("stato", "Livré").order("created_at")
        
        if role == 'barman':
            query = query.eq("stato", "À préparer")
        elif role == 'serveuse':
            query = query.or_("stato.eq.À encaisser,stato.eq.Prêt au bar")

        commandes = query.execute().data

        for cmd in commandes:
            cmd['ordine_testo'] = format_ordine_text(cmd['ordine'])
            cmd.pop('prenotazione_id', None)

        response_data = {'commandes': commandes}

        # Calcolo cassa live per la serveuse
        if role == 'serveuse' and nome:
            ordini_serveuse = local_supabase.table("commandes_bar").select("totale").eq("serveuse", nome).execute().data
            versamenti = local_supabase.table("versements_caisse").select("importo").eq("serveuse", nome).execute().data
            totale_incassato = sum([o['totale'] for o in ordini_serveuse])
            totale_versato = sum([v['importo'] for v in versamenti])
            response_data['cassa'] = totale_incassato - totale_versato
            
        # Invio dello stock live per il barman
        if role == 'barman':
            inventario = local_supabase.table("inventario").select("*").execute().data
            response_data['stock'] = {item['item_id']: item['quantita'] for item in inventario}

        return jsonify(response_data)

    except Exception as e:
        print(f"Errore Polling Staff: {e}")
        return jsonify({'error': str(e)}), 500


# ----------------- ROTTE PUBBLICHE CLIENT ----------------- #

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        email = request.form.get('email')
        telefono = request.form.get('telefono')

        esistenza = supabase.table("prenotazioni").select("id").or_(f"email.eq.{email},telefono.eq.{telefono}").execute()

        if esistenza.data:
            flash('Un billet a déjà été réservé avec cet email ou ce numéro.', 'error')
            return redirect(url_for('home'))

        caratteri = string.ascii_uppercase + string.digits
        nuovo_codice_cliente = ''.join(random.choices(caratteri, k=4))

        response = supabase.table("prenotazioni").insert({
            "nome": request.form.get('nome'),
            "email": email,
            "telefono": telefono,
            "stato": "In attesa",
            "codice_cliente": nuovo_codice_cliente
        }).execute()
        
        if response.data:
            session.permanent = True
            session['user_id'] = response.data[0]['id']
            return redirect(url_for('user_dashboard'))
            
    utente_connesso = 'user_id' in session
    return render_template('index.html', is_logged_in=utente_connesso)

@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login_user.html')

@app.route('/login_user', methods=['POST'])
def login_user():
    email = request.form.get('email')
    telefono = request.form.get('telefono')
    
    try:
        response = supabase.table("prenotazioni")\
            .select("id, email, telefono")\
            .eq("email", email)\
            .eq("telefono", telefono)\
            .limit(1)\
            .execute()
        
        if response.data:
            session.permanent = True
            session['user_id'] = response.data[0]['id']
            return redirect(url_for('user_dashboard'))
        else:
            flash('Email ou numéro de téléphone incorrect.', 'error')
            return redirect(url_for('login_page'))
            
    except Exception as e:
        flash('Erreur de connexion au serveur.', 'error')
        return redirect(url_for('login_page'))


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

# ---------------------------------------------------------
# GESTIONE CARRELLO E STORICO ORDINI (DASHBOARD)
# ---------------------------------------------------------

@app.route('/dashboard')
def user_dashboard():
    if 'user_id' not in session: 
        return redirect(url_for('login_page'))

    # Creazione di un client locale per il caricamento principale
    # previene il blocco del socket se il polling JS si attiva contemporaneamente
    local_supabase = create_client(url, key)

    response = local_supabase.table("prenotazioni").select("*").eq("id", session['user_id']).execute()
    
    if not response.data:
        session.pop('user_id', None)
        return redirect(url_for('login_page'))

    user_data = response.data[0]
    tier_bar = user_data.get('tier_bar', 'Classique')

    # Recupera lo storico degli ordini utilizzando il client locale isolato
    storico_response = local_supabase.table("commandes_bar").select("id, totale, stato, ordine, created_at").eq("prenotazione_id", session['user_id']).order("created_at", desc=True).execute()
    storico_ordini = storico_response.data if storico_response.data else []

    # Formatta il JSON di ogni ordine in un testo leggibile per l'interfaccia utente
    for ordine in storico_ordini:
        ordine['dettagli_testo'] = format_ordine_text(ordine['ordine'])

    return render_template('user_dashboard.html', 
                           user=list(user_data.values()), 
                           storico_ordini=storico_ordini,
                           tier_bar=tier_bar)


@app.route('/resume_commande', methods=['POST'])
def resume_commande():
    """Mostra il riepilogo dell'ordine prima della conferma definitiva e controlla minuziosamente le scorte."""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    cart_json = request.form.get('cart_data', '{}')
    tavolo_inviato = request.form.get('tavolo')

    try:
        cart_data = json.loads(cart_json)
    except:
        cart_data = {}

    if not cart_data or not tavolo_inviato:
        flash('Une erreur est survenue avec votre panier.', 'error')
        return redirect(url_for('afficher_panier'))

    # Creazione di un client locale per evitare WinError 10035 su Windows
    local_supabase = create_client(url, key)

    # SALVATAGGIO IMMEDIATO: Salviamo il carrello provvisorio prima dei controlli. 
    # Così, se lo stock manca e ricarichiamo la pagina, il cliente ritrova i suoi numeri e non si azzera.
    local_supabase.table("prenotazioni").update({"ordini_bar": cart_data}).eq("id", session['user_id']).execute()

    try:
        stock_response = local_supabase.table("inventario").select("*").execute().data
        stock_db = {item['item_id']: item['quantita'] for item in stock_response}
    except Exception as e:
        print(f"Errore caricamento inventario in resume: {e}")
        stock_db = {}

    total_calcolato = 0
    carrello_validato = {}
    boissons_details = []

    for item_id, qty in cart_data.items():
        if qty > 0 and item_id in INVENTORY:
            
            # Verifica Stock con messaggi di errore mirati
            stock_dispo = stock_db.get(item_id, 0)
            if qty > stock_dispo:
                nom_produit = INVENTORY[item_id]['name']
                
                # Messaggio preciso sulle quantità mancanti
                if stock_dispo == 0:
                    flash(f"Rupture de stock : {nom_produit} est épuisé.", 'error')
                else:
                    flash(f"Stock insuffisant pour {nom_produit}. Vous en avez demandé {qty}, mais il n'en reste que {stock_dispo} au bar.", 'error')
                
                return redirect(url_for('afficher_panier'))

            carrello_validato[item_id] = qty
            item = INVENTORY[item_id]
            
            # Calcolo del prezzo considerando eventuali bundle (es: 3 per 10€)
            if 'bundleQty' in item and 'bundlePrice' in item:
                bundles = qty // item['bundleQty']
                remainder = qty % item['bundleQty']
                line_total = (bundles * item['bundlePrice']) + (remainder * item['price'])
            else:
                line_total = qty * item['price']
            
            total_calcolato += line_total
            boissons_details.append({
                'name': item['name'],
                'qty': qty,
                'line_total': line_total
            })

    if total_calcolato <= 0:
        flash('Votre panier sembra vuoto.', 'error')
        return redirect(url_for('afficher_panier'))

    return render_template('resume_commande.html', 
                           boissons_details=boissons_details, 
                           total=total_calcolato, 
                           tavolo=tavolo_inviato,
                           cart_json=json.dumps(carrello_validato))


# ---------------------------------------------------------


@app.route('/confirmer_commande', methods=['POST'])
def confirmer_commande():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_id = session['user_id']
    local_supabase = create_client(url, key)
    
    user_response = local_supabase.table("prenotazioni").select("nome").eq("id", user_id).execute()
    if not user_response.data:
        return redirect(url_for('login_page'))
    
    nome_cliente = user_response.data[0]['nome']
    cart_json = request.form.get('cart_data', '{}')
    tavolo_inviato = request.form.get('tavolo')
    total = request.form.get('total')

    try:
        cart_data = json.loads(cart_json)
        total_calcolato = float(total)
    except:
        flash('Erreur de traitement des données.', 'error')
        return redirect(url_for('afficher_panier'))

    nuova_commande_live = {
        "prenotazione_id": user_id,
        "nome_cliente": nome_cliente,
        "tavolo": tavolo_inviato,
        "ordine": cart_data,
        "totale": total_calcolato,
        "stato": "À encaisser" 
    }

    try:
        local_supabase.table("commandes_bar").insert(nuova_commande_live).execute()
        local_supabase.table("prenotazioni").update({"ordini_bar": {}}).eq("id", user_id).execute()
        
        # Sottrazione dall'inventario
        stock_response = local_supabase.table("inventario").select("*").execute().data
        stock_db = {item['item_id']: item['quantita'] for item in stock_response}
        
        for item_id, qty in cart_data.items():
            current_stock = stock_db.get(item_id, 0)
            new_stock = max(0, current_stock - qty)
            local_supabase.table("inventario").upsert({"item_id": item_id, "quantita": new_stock}).execute()
        
        flash('Commande envoyée ! Une serveuse arrive à votre table.', 'success')
    except Exception as e:
        print(f"Errore conferma: {e}")
        flash('Une erreur technique est survenue.', 'error')

    return redirect(url_for('user_dashboard'))

@app.route('/staff/action/update_stock', methods=['POST'])
def update_stock():
    """Permet au barman de mettre à jour la quantité d'une boisson en magasin."""
    if 'staff_role' not in session or session['staff_role'] != 'barman':
        return redirect(url_for('login_staff'))
        
    item_id = request.form.get('item_id')
    qty = int(request.form.get('quantita', 0))
    
    try:
        supabase.table("inventario").upsert({"item_id": item_id, "quantita": qty}).execute()
        flash('Stock mis à jour avec succès.', 'success')
    except Exception as e:
        flash('Erreur lors de la mise à jour du stock.', 'error')
        
    return redirect(url_for('barman_dashboard'))


@app.route('/panier_bar', methods=['GET'])
def afficher_panier():
    if 'user_id' not in session: return redirect(url_for('login_page'))
    
    user_data = supabase.table("prenotazioni").select("stato, ordini_bar").eq("id", session['user_id']).execute().data[0]
    
    if user_data['stato'] == 'In attesa':
        flash('Veuillez payer votre ticket pour accéder au bar.', 'error')
        return redirect(url_for('user_dashboard'))
        
    existing_cart = user_data.get('ordini_bar') or {}

    PRODOTTI_ATTIVI = [
        'eau', 'coca', 'san_pellegrino', 'redbull', 'malta',
        'fior_arancio', 'colli_eugani', 'martini', 'ca_de_mari', 'colligny', 'moet', 'veuve', 'ruinart',
        'vecchia_romagna', 'bailey', 'black_label', 'gold_label', 'chivas_18',
        'brochettes'
    ]
    cleaned_cart = {k: v for k, v in existing_cart.items() if k in PRODOTTI_ATTIVI and v > 0}
    
    return render_template('panier_bar.html', existing_cart=cleaned_cart)

@app.route('/valider_panier', methods=['POST'])
def valider_panier():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_id = session['user_id']
    
    user_response = supabase.table("prenotazioni").select("nome").eq("id", user_id).execute()
    if not user_response.data:
        session.pop('user_id', None)
        return redirect(url_for('login_page'))
    
    nome_cliente = user_response.data[0]['nome']
    cart_json = request.form.get('cart_data', '{}')
    tavolo_inviato = request.form.get('tavolo')
    
    try:
        cart_data = json.loads(cart_json)
    except:
        cart_data = {}

    if not cart_data or not tavolo_inviato:
        flash('Une erreur est survenue lors de la commande.', 'error')
        return redirect(url_for('afficher_panier'))

    total_calcolato = 0
    carrello_validato = {}
    
    for item_id, qty in cart_data.items():
        if qty > 0 and item_id in INVENTORY:
            carrello_validato[item_id] = qty
            item = INVENTORY[item_id]
            if 'bundleQty' in item and 'bundlePrice' in item:
                bundles = qty // item['bundleQty']
                remainder = qty % item['bundleQty']
                total_calcolato += (bundles * item['bundlePrice']) + (remainder * item['price'])
            else:
                total_calcolato += qty * item['price']

    if total_calcolato <= 0:
        flash('Votre panier semble vide.', 'error')
        return redirect(url_for('afficher_panier'))

    nuova_commande_live = {
        "prenotazione_id": user_id,
        "nome_cliente": nome_cliente,
        "tavolo": tavolo_inviato,
        "ordine": carrello_validato,
        "totale": total_calcolato,
        "stato": "À encaisser" 
    }

    try:
        supabase.table("commandes_bar").insert(nuova_commande_live).execute()
        flash('Votre commande a été validée ! Une serveuse arrive.', 'success')
    except Exception as e:
        print(f"Errore inserimento: {e}")
        flash('Une erreur technique est survenue.', 'error')

    return redirect(url_for('user_dashboard'))


# ---------------------------------------------------------
# ROTTE DI REINDIRIZZAMENTO E LOGOUT STAFF (STUBS EVITA BUILDERROR)
# ---------------------------------------------------------

@app.route('/staff/login', methods=['GET', 'POST'])
def login_staff():
    """Gestisce il login per il personale e reindirizza in base al ruolo."""
    if request.method == 'POST':
        nome_staff = request.form.get('nome_staff')
        password = request.form.get('password')

        # Determina il ruolo controllando se la password corrisponde a una nel dizionario
        ruolo_trovato = None
        for role, pwd in STAFF_PASSWORDS.items():
            if password == pwd:
                ruolo_trovato = role
                break
        
        if ruolo_trovato:
            # Salva il ruolo e il nome nella sessione per le azioni future
            session['staff_role'] = ruolo_trovato
            session['staff_nome'] = nome_staff
            
            # Reindirizzamento automatico alla dashboard corretta
            if ruolo_trovato == 'serveuse':
                return redirect(url_for('serveuse_dashboard'))
            elif ruolo_trovato == 'barman':
                return redirect(url_for('barman_dashboard'))
            elif ruolo_trovato == 'caisse':
                return redirect(url_for('caisse_dashboard'))
        else:
            # Password errata, ricarica la pagina con un errore
            flash('Mot de passe incorrect. Accès refusé.', 'error')
            return redirect(url_for('login_staff'))

    return render_template('login_staff.html')

@app.route('/staff/serveuse')
def serveuse_dashboard():
    """Passa l'inventario alla dashboard per visualizzare il menu."""
    if 'staff_role' not in session or session['staff_role'] != 'serveuse':
        return redirect(url_for('login_staff'))
    return render_template('serveuse_dashboard.html', inventory=INVENTORY)

@app.route('/staff/barman')
def barman_dashboard():
    """Pannello tablet del barman con gestione coda e inventario."""
    if 'staff_role' not in session or session['staff_role'] != 'barman':
        return redirect(url_for('login_staff'))
        
    # Recupera le scorte attuali dal database per popolare i campi
    try:
        stock_response = supabase.table("inventario").select("*").execute().data
        stock_db = {item['item_id']: item['quantita'] for item in stock_response}
    except Exception as e:
        print(f"Errore caricamento inventario: {e}")
        stock_db = {}

    return render_template('barman_dashboard.html', inventory=INVENTORY, stock_db=stock_db)


@app.route('/staff/action/update_stock_bulk', methods=['POST'])
def update_stock_bulk():
    """Aggiornamento massivo di tutto l'inventario da parte del barman."""
    if 'staff_role' not in session or session['staff_role'] != 'barman':
        return redirect(url_for('login_staff'))
        
    try:
        # Cicla su tutti i prodotti dell'inventario per prendere i nuovi valori dal form
        for item_id in INVENTORY.keys():
            qty_str = request.form.get(f'stock_{item_id}')
            if qty_str is not None:
                qty = int(qty_str)
                # Esegue un upsert: inserisce se non esiste, aggiorna se esiste
                supabase.table("inventario").upsert({"item_id": item_id, "quantita": qty}).execute()
                
        flash('Inventaire mis à jour avec succès.', 'success')
    except Exception as e:
        print(f"Errore aggiornamento stock: {e}")
        flash('Erreur lors de la mise à jour du stock.', 'error')
        
    # Ritorna alla pagina forzando l'apertura del tab inventario
    return redirect(url_for('barman_dashboard') + '?tab=inventaire')

@app.route('/staff/caisse')
def caisse_dashboard():
    if 'staff_role' not in session or session['staff_role'] != 'caisse':
        return redirect(url_for('login_staff'))
        
    try:
        tutti_ordini = supabase.table("commandes_bar").select("serveuse, totale").execute().data
        ordini = [o for o in tutti_ordini if o.get('serveuse')]
        
        versamenti = supabase.table("versements_caisse").select("serveuse, importo").execute().data
        
        finances = {}
        totale_cassa_generale = 0 # NOUVEAU : Total de la caisse
        
        for o in ordini:
            s = o['serveuse']
            if s not in finances:
                finances[s] = {'incassato': 0, 'versato': 0, 'da_versare': 0}
            finances[s]['incassato'] += o['totale']
            
        for v in versamenti:
            s = v['serveuse']
            if s not in finances:
                finances[s] = {'incassato': 0, 'versato': 0, 'da_versare': 0}
            finances[s]['versato'] += v['importo']
            totale_cassa_generale += v['importo'] # NOUVEAU : Ajout au total global
            
        for s in finances:
            finances[s]['da_versare'] = finances[s]['incassato'] - finances[s]['versato']
            
        return render_template('caisse_dashboard.html', finances=finances, totale_cassa_generale=totale_cassa_generale)
        
    except Exception as e:
        print(f"Errore caricamento cassa: {e}")
        flash('Une erreur est survenue.', 'error')
        return redirect(url_for('login_staff'))

@app.route('/staff/logout')
def staff_logout():
    session.pop('staff_role', None)
    session.pop('staff_nome', None)
    return redirect(url_for('login_staff'))


# ---------------------------------------------------------
# AZIONI WORKFLOW LIVE STAFF (CON GESTIONE CONCORRENZA)
# ---------------------------------------------------------

@app.route('/staff/action/encaisse/<int:order_id>')
def staff_action_encaisse(order_id):
    """Serveuse valida pagamento: 'À encaisser' -> 'À préparer'"""
    if 'staff_role' not in session or session['staff_role'] != 'serveuse':
        return redirect(url_for('login_staff'))

    serveuse_nome = session.get('staff_nome', 'Serveuse')

    try:
        # GESTIONE CONCORRENZA: Aggiorna solo se lo stato è ancora 'À encaisser'
        response = supabase.table("commandes_bar")\
            .update({"stato": "À préparer", "serveuse": serveuse_nome})\
            .eq("id", order_id)\
            .eq("stato", "À encaisser")\
            .execute()

        if response.data:
            flash(f'Commande #{order_id} encaissée. Envoyée au Barman.', 'success')
        else:
            flash(f'Désolé, la commande #{order_id} a déjà été prise en charge par une collègue.', 'error')
            
    except Exception as e:
        flash(f'Errore tecnico durante l\'incasso.', 'error')
        print(f"Errore Action Encaisse: {e}")

    return redirect(url_for('serveuse_dashboard'))


@app.route('/staff/action/prete/<int:order_id>')
def staff_action_prete(order_id):
    """Barman segna come pronto: 'À préparer' -> 'Prêt au bar'"""
    if 'staff_role' not in session or session['staff_role'] != 'barman':
        return redirect(url_for('login_staff'))

    try:
        response = supabase.table("commandes_bar")\
            .update({"stato": "Prêt au bar"})\
            .eq("id", order_id)\
            .eq("stato", "À préparer")\
            .execute()

        if response.data:
            flash(f'Commande #{order_id} signalée comme PRÊTE au bar.', 'success')
        else:
            flash(f'Impossibile aggiornare la commande #{order_id}.', 'error')

    except Exception as e:
        flash(f'Errore tecnico al bar.', 'error')
        print(f"Errore Action Prete: {e}")

    return redirect(url_for('barman_dashboard'))


@app.route('/staff/action/livre/<int:order_id>')
def staff_action_livre(order_id):
    """Serveuse segna come consegnato: 'Prêt au bar' -> 'Livré'"""
    if 'staff_role' not in session or session['staff_role'] != 'serveuse':
        return redirect(url_for('login_staff'))

    try:
        response = supabase.table("commandes_bar")\
            .update({"stato": "Livré"})\
            .eq("id", order_id)\
            .eq("stato", "Prêt au bar")\
            .execute()

        if response.data:
            flash(f'Commande #{order_id} LIVRÉE et clôturée.', 'success')
        else:
            flash(f'Impossibile chiudere la commande #{order_id}.', 'error')

    except Exception as e:
        flash(f'Errore tecnico durante la consegna.', 'error')
        print(f"Errore Action Livre: {e}")

    return redirect(url_for('serveuse_dashboard'))


# ---------------------------------------------------------
# GESTIONE CASH CASSA (AGGIORNAMENTO SOLDI SERVEUSE - Paule, Murielle...)
# ---------------------------------------------------------

@app.route('/staff/action/versement', methods=['POST'])
def staff_action_versement():
    """Il supervisore registra che una serveuse ha consegnato una parte dei soldi"""
    if 'staff_role' not in session or session['staff_role'] != 'caisse':
        return redirect(url_for('login_staff'))

    serveuse_target = request.form.get('serveuse_nome')
    importo_versato = request.form.get('importo', 0)

    try:
        importo_float = float(importo_versato)
        if importo_float <= 0:
            flash('Veuillez entrer un montant valide.', 'error')
            return redirect(url_for('caisse_dashboard'))

        # Inserimento del verdetto parziale nella tabella dei versamenti su Supabase
        dati_versamento = {
            "serveuse": serveuse_target,
            "importo": importo_float
        }
        # Nota: Assumiamo che la tabella 'versements_caisse' sia creata o gestita via SQL
        supabase.table("versements_caisse").insert(dati_versamento).execute()
        
        flash(f'Le versement de {importo_float}€ per {serveuse_target} è stato registrato con successo.', 'success')

    except Exception as e:
        flash('Erreur lors de l\'enregistrement du versement par la caisse.', 'error')
        print(f"Errore Versement Caisse: {e}")

    return redirect(url_for('caisse_dashboard'))


# ----------------- ROTTE AMMINISTRATORE GENERALI ----------------- #

@app.route('/admin')
def admin_page(): return render_template('login_admin.html')

@app.route('/admin_login', methods=['POST'])
def admin_login():
    if request.form.get('password') == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return redirect(url_for('admin_dashboard'))
    flash('Mot de passe incorrect.', 'admin_error')
    return redirect(url_for('admin_page'))

@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    
    # 1. Recupera tutte le prenotazioni
    data = supabase.table("prenotazioni").select("*").order("id", desc=True).execute().data
    
    # 2. Recupera TUTTI gli ordini confermati nella tabella commandes_bar
    ordini_data = supabase.table("commandes_bar").select("prenotazione_id, totale, ordine").execute().data
    
    # 3. Raggruppa gli ordini per ogni cliente (Somma totale e dettagli testuali)
    ordini_per_utente = {}
    dettagli_per_utente = {}
    
    for ord in ordini_data:
        pid = ord['prenotazione_id']
        if pid not in ordini_per_utente:
            ordini_per_utente[pid] = 0
            dettagli_per_utente[pid] = []
        
        ordini_per_utente[pid] += ord['totale']
        
        # Format les détails de cette commande spécifique
        testo_ordine = format_ordine_text(ord['ordine'])
        if testo_ordine:
            dettagli_per_utente[pid].append(testo_ordine)
    
    # 4. Statistiche generali
    stats = {
        'total': len(data),
        'confirmes': len([p for p in data if p['stato'] in ['Confirmé', 'Présent']]),
        'en_attente': len([p for p in data if p['stato'] == 'In attesa']),
        'presents': len([p for p in data if p['stato'] == 'Présent'])
    }
    
    query = request.args.get('q', '').lower()
    if query:
        data = [p for p in data if 
                query in str(p.get('nome', '')).lower() or 
                query in str(p.get('telefono', '')).lower() or 
                query in str(p.get('codice_cliente', '')).lower() or 
                query in str(p.get('code_qr', '')).lower()]
    
    prenotazioni = []
    
    # 5. Costruzione dei dati per la tabella HTML
    for p in data:
        # Prende il totale reale dalla tabella commandes_bar
        total_bar = ordini_per_utente.get(p['id'], 0)
        
        # Unisce tutte le bevande ordinate in diverse mandate con un separatore " | "
        dettagli_uniti = " | ".join(dettagli_per_utente.get(p['id'], []))

        prenotazioni.append([
            p['id'], p['nome'], p['email'], p['telefono'], p['stato'], 
            p.get('code_qr'), p.get('codice_cliente'), total_bar, 
            p.get('tier_bar', 'Classique'), dettagli_uniti
        ])
    
    return render_template('admin_dashboard.html', prenotazioni=prenotazioni, stats=stats, search_query=query)

@app.route('/admin/valider/<int:id>')
def admin_valider(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    nuovo_code = secrets.token_hex(3).upper()
    supabase.table("prenotazioni").update({"stato": "Confirmé", "code_qr": nuovo_code}).eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/set_tier/<int:id>/<tier>')
def admin_set_tier(id, tier):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    if tier in ['Classique', 'Premium', 'VIP']:
        supabase.table("prenotazioni").update({"tier_bar": tier}).eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/scan_manual/<code>')
def scan_manual(code):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    user = supabase.table("prenotazioni").select("*").eq("code_qr", code).execute().data
    
    if user:
        stato_attuale = user[0]['stato']
        tier_bar = user[0].get('tier_bar', 'Classique')
        
        if stato_attuale == 'Confirmé':
            supabase.table("prenotazioni").update({"stato": "Présent"}).eq("code_qr", code).execute()
            return render_template('scan_result.html', status='success', message=f"Accès autorisé !", tier=tier_bar)
            
        elif stato_attuale == 'Présent':
            return render_template('scan_result.html', status='warning', message=f"Attention : Le billet de {user[0]['nome']} a DÉJÀ ÉTÉ SCANNÉ.", tier=tier_bar)
            
        else:
            return render_template('scan_result.html', status='error', message="Billet non valide ou suspendu.")
            
    return render_template('scan_result.html', status='error', message="Code invalide ou introuvable.")

@app.route('/admin/suspendre/<int:id>')
def admin_suspendre(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    supabase.table("prenotazioni").update({"stato": "Suspendu", "code_qr": None}).eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/supprimer/<int:id>')
def admin_supprimer(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    supabase.table("prenotazioni").delete().eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_page'))

if __name__ == '__main__':
    app.run(debug=True)
