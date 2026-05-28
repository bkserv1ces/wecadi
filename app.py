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
    'moet': {'name': 'Moët', 'price': 100},
    'veuve': {'name': 'Veuve Clicquot', 'price': 100},
    'belaire': {'name': 'Luc Belaire', 'price': 80},
    'colligny': {'name': 'Colligny', 'price': 75},
    'prosecco': {'name': 'Prosecco', 'price': 30},
    'spumante': {'name': 'Spumante', 'price': 30},
    'gold': {'name': 'Gold', 'price': 100},
    'black_label': {'name': 'Black Label', 'price': 75},
    'jack_daniel': {'name': "Jack Daniel's", 'price': 70},
    'vecchia_romagna': {'name': 'Vecchia Romagna', 'price': 50},
    'baileys': {'name': 'Baileys', 'price': 50},
    'redbull': {'name': 'Redbull', 'price': 4, 'bundleQty': 3, 'bundlePrice': 10},
    'coca': {'name': 'Coca', 'price': 5, 'bundleQty': 3, 'bundlePrice': 10},
    'malta': {'name': 'Malta', 'price': 5},
    'eau': {'name': 'Eau', 'price': 2, 'bundleQty': 3, 'bundlePrice': 5}
}


# Inizializzazione Supabase
url: str = "https://nujvctqiggtxyeewvexu.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im51anZjdHFpZ2d0eHllZXd2ZXh1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTI5OTE3NCwiZXhwIjoyMDk0ODc1MTc0fQ.nwJXQxvj8YNWjZnEoWd0len471k2sjJa2BlUfGxDk6U"
supabase: Client = create_client(url, key)

app = Flask(__name__)
app.secret_key = 'wecadi_prestige_key_2026'

# Imposta la durata della sessione a 90 giorni per ricordare l'utente
app.permanent_session_lifetime = timedelta(days=90)

# Password fissa per l'amministratore
ADMIN_PASSWORD = 'w26-wecadi'

# ----------------- API TEMPS RÉEL (POLLING) ----------------- #

@app.route('/api/live_status')
def api_live_status():
    if 'user_id' not in session:
        return jsonify({'error': 'Non autorisé'}), 401
    
    try:
        # Recupera sia lo stato del biglietto sia il livello del bar
        user_data = supabase.table("prenotazioni").select("stato, tier_bar").eq("id", session['user_id']).execute().data[0]
        
        return jsonify({
            'stato': user_data.get('stato', 'In attesa'),
            'tier_bar': user_data.get('tier_bar', 'Classique')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# ----------------- ROTTE PUBBLICHE ----------------- #

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        email = request.form.get('email')
        telefono = request.form.get('telefono')

        # Controllo se esiste già una prenotazione con questa email o questo telefono
        esistente = supabase.table("prenotazioni").select("id").or_(f"email.eq.{email},telefono.eq.{telefono}").execute()

        if esistente.data:
            # Se esiste già, inviamo un messaggio di errore alla pagina
            flash('Un billet a déjà été réservé avec cet email ou ce numéro.', 'error')
            return redirect(url_for('home'))

        # Generazione di un codice alfanumerico univoco di 4 caratteri
        caratteri = string.ascii_uppercase + string.digits
        nuovo_codice_cliente = ''.join(random.choices(caratteri, k=4))

        # Inserimento della prenotazione con il nuovo codice cliente
        response = supabase.table("prenotazioni").insert({
            "nome": request.form.get('nome'),
            "email": email,
            "telefono": telefono,
            "stato": "In attesa",
            "codice_cliente": nuovo_codice_cliente
        }).execute()
        
        # Login automatico immediato dopo l'inserimento
        if response.data:
            session.permanent = True
            session['user_id'] = response.data[0]['id']
            return redirect(url_for('user_dashboard'))
            
    # Controlla se l'utente è già loggato per passarlo al template HTML
    utente_connesso = 'user_id' in session
    return render_template('index.html', is_logged_in=utente_connesso)

@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login_user.html')

@app.route('/login_user', methods=['POST'])
def login_user():
    email = request.form.get('email')
    telefono = request.form.get('telefono')
    
    # Ottimizzazione: seleziona solo i campi necessari e usa un filtro rigoroso
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
    # Rimozione dell'ID utente dalla sessione
    session.pop('user_id', None)
    return redirect(url_for('home'))

@app.route('/dashboard')
def user_dashboard():
    # Controllo di sicurezza
    if 'user_id' not in session: return redirect(url_for('login_page'))
    user_data = supabase.table("prenotazioni").select("*").eq("id", session['user_id']).execute().data[0]
    
    # Calcolo del riepilogo bevande
    ordini_bar = user_data.get('ordini_bar') or {}
    boissons_details = []
    total_bar = 0
    
    for item_id, qty in ordini_bar.items():
        if qty > 0 and item_id in INVENTORY:
            item = INVENTORY[item_id]
            # Calcolo considerando le promozioni (es. 3 per 10€)
            if 'bundleQty' in item and 'bundlePrice' in item:
                bundles = qty // item['bundleQty']
                remainder = qty % item['bundleQty']
                line_total = (bundles * item['bundlePrice']) + (remainder * item['price'])
            else:
                line_total = qty * item['price']
                
            total_bar += line_total
            boissons_details.append({
                'name': item['name'],
                'qty': qty,
                'line_total': line_total
            })
            tier_bar = user_data.get('tier_bar', 'Classique')
    return render_template('user_dashboard.html', 
                           user=list(user_data.values()), 
                           boissons_details=boissons_details, 
                           total_bar=total_bar,
                           tier_bar=tier_bar)

@app.route('/panier_bar', methods=['GET'])
def afficher_panier():
    if 'user_id' not in session: return redirect(url_for('login_page'))
    # Recupero degli ordini esistenti per pre-compilare il carrello
    user_data = supabase.table("prenotazioni").select("ordini_bar").eq("id", session['user_id']).execute().data[0]
    existing_cart = user_data.get('ordini_bar') or {}
    
    return render_template('panier_bar.html', existing_cart=existing_cart)

@app.route('/valider_panier', methods=['POST'])
def valider_panier():
    if 'user_id' not in session: return redirect(url_for('login_page'))
    cart_data_json = request.form.get('cart_data')
    
    if cart_data_json:
        cart = json.loads(cart_data_json)
        supabase.table("prenotazioni").update({"ordini_bar": cart}).eq("id", session['user_id']).execute()
        
    # Reindirizzamento al dashboard con il parametro per aprire direttamente la scheda "boissons"
    return redirect(url_for('user_dashboard', tab='boissons'))

# ----------------- ROTTE AMMINISTRATORE ----------------- #

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
    # Controllo di sicurezza
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    
    data = supabase.table("prenotazioni").select("*").order("id", desc=True).execute().data
    
    stats = {
        'total': len(data),
        'confirmes': len([p for p in data if p['stato'] in ['Confirmé', 'Présent']]),
        'en_attente': len([p for p in data if p['stato'] == 'In attesa']),
        'presents': len([p for p in data if p['stato'] == 'Présent'])
    }
    
    query = request.args.get('q', '').lower()
    if query:
        # Ricerca limitata solo a: Nome, Telefono, Codice Cliente e Code QR
        data = [p for p in data if 
                query in str(p.get('nome', '')).lower() or 
                query in str(p.get('telefono', '')).lower() or 
                query in str(p.get('codice_cliente', '')).lower() or 
                query in str(p.get('code_qr', '')).lower()]
    
    # Inizializza la lista vuota per il template
    prenotazioni = []
    
    # Ciclo su tutti gli utenti filtrati per calcolare i dettagli
    for p in data:
        ordini_bar = p.get('ordini_bar') or {}
        total_bar = 0
        dettagli_bar = []
        
        # Calcolo del totale bar e riepilogo testuale per questo specifico utente
        for item_id, qty in ordini_bar.items():
            if qty > 0 and item_id in INVENTORY:
                item = INVENTORY[item_id]
                if 'bundleQty' in item and 'bundlePrice' in item:
                    bundles = qty // item['bundleQty']
                    remainder = qty % item['bundleQty']
                    total_bar += (bundles * item['bundlePrice']) + (remainder * item['price'])
                else:
                    total_bar += qty * item['price']
                dettagli_bar.append(f"{qty}x {item['name']}")

        # Aggiunta alla lista finale
        prenotazioni.append([
            p['id'],                 # 0
            p['nome'],               # 1
            p['email'],              # 2
            p['telefono'],           # 3
            p['stato'],              # 4
            p.get('code_qr'),        # 5
            p.get('codice_cliente'), # 6
            total_bar,               # 7: Totale in Euro per il bar
            p.get('tier_bar', 'Classique'), # 8: Livello Scelto (Classique, Premium, VIP)
            ", ".join(dettagli_bar)  # 9: Dettaglio testuale
        ])
    
    return render_template('admin_dashboard.html', prenotazioni=prenotazioni, stats=stats, search_query=query)

@app.route('/admin/valider/<int:id>')
def admin_valider(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    
    # Generazione del codice esadecimale unico (senza salvare file fisici)
    nuovo_code = secrets.token_hex(3).upper()

    # Aggiornamento dello stato nel database
    supabase.table("prenotazioni").update({"stato": "Confirmé", "code_qr": nuovo_code}).eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/set_tier/<int:id>/<tier>')
def admin_set_tier(id, tier):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    
    # Aggiorna il livello solo se è uno dei tre validi
    if tier in ['Classique', 'Premium', 'VIP']:
        supabase.table("prenotazioni").update({"tier_bar": tier}).eq("id", id).execute()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/scan_manual/<code>')
def scan_manual(code):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    
    user = supabase.table("prenotazioni").select("*").eq("code_qr", code).execute().data
    
    if user:
        # Controllo dello stato per gestire il flusso dello scanner
        stato_attuale = user[0]['stato']
        
        # Recupera il livello del bar dal database (default: Classique)
        tier_bar = user[0].get('tier_bar', 'Classique')
        
        if stato_attuale == 'Confirmé':
            # Il biglietto è valido: aggiorna lo stato a Presente
            supabase.table("prenotazioni").update({"stato": "Présent"}).eq("code_qr", code).execute()
            return render_template('scan_result.html', status='success', message=f"Accès autorisé !", tier=tier_bar)
            
        elif stato_attuale == 'Présent':
            # Il biglietto è già stato scansionato in precedenza
            return render_template('scan_result.html', status='warning', message=f"Attention : Le billet de {user[0]['nome']} a DÉJÀ ÉTÉ SCANNÉ.", tier=tier_bar)
            
        else:
            # Se è in attesa o sospeso (non mostriamo il livello bar se non può entrare)
            return render_template('scan_result.html', status='error', message="Billet non valide ou suspendu.")
            
    return render_template('scan_result.html', status='error', message="Code invalide ou introuvable.")

@app.route('/admin/suspendre/<int:id>')
def admin_suspendre(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    # Sospensione dell'utente (nessun file da eliminare)
    supabase.table("prenotazioni").update({"stato": "Suspendu", "code_qr": None}).eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/supprimer/<int:id>')
def admin_supprimer(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    # Eliminazione dell'utente dal database (nessun file da eliminare)
    supabase.table("prenotazioni").delete().eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_page'))

if __name__ == '__main__':
    app.run(debug=True)