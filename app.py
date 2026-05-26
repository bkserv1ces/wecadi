import os
import secrets
import string
import random
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client, Client

# Inizializzazione Supabase
url: str = "https://nujvctqiggtxyeewvexu.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im51anZjdHFpZ2d0eHllZXd2ZXh1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTI5OTE3NCwiZXhwIjoyMDk0ODc1MTc0fQ.nwJXQxvj8YNWjZnEoWd0len471k2sjJa2BlUfGxDk6U"
supabase: Client = create_client(url, key)

app = Flask(__name__)
app.secret_key = 'wecadi_prestige_key_2026'

# Imposta la durata della sessione a 90 giorni per ricordare l'utente
app.permanent_session_lifetime = timedelta(days=90)

# Password fissa per l'amministratore
ADMIN_PASSWORD = 'wecadi2026'

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

@app.route('/dashboard')
def user_dashboard():
    # Controllo di sicurezza per l'utente
    if 'user_id' not in session: return redirect(url_for('login_page'))
    user_data = supabase.table("prenotazioni").select("*").eq("id", session['user_id']).execute().data[0]
    return render_template('user_dashboard.html', user=list(user_data.values()))

@app.route('/logout')
def logout():
    # Rimozione dell'ID utente dalla sessione
    session.pop('user_id', None)
    return redirect(url_for('home'))

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
    
    # Aggiunta del codice_cliente (indice 6) nella lista inviata al template HTML
    prenotazioni = [[
        p['id'], 
        p['nome'], 
        p['email'], 
        p['telefono'], 
        p['stato'], 
        p.get('code_qr'),
        p.get('codice_cliente') # Nuovo campo aggiunto all'indice 6
    ] for p in data]
    
    return render_template('admin_dashboard.html', prenotazioni=prenotazioni, stats=stats, search_query=query)

@app.route('/admin/valider/<int:id>')
def admin_valider(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    
    # Generazione del codice esadecimale unico (senza salvare file fisici)
    nuovo_code = secrets.token_hex(3).upper()

    # Aggiornamento dello stato nel database
    supabase.table("prenotazioni").update({"stato": "Confirmé", "code_qr": nuovo_code}).eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/scan_manual/<code>')
def scan_manual(code):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    
    user = supabase.table("prenotazioni").select("*").eq("code_qr", code).execute().data
    
    if user:
        # Controllo dello stato per gestire il flusso dello scanner
        stato_attuale = user[0]['stato']
        
        if stato_attuale == 'Confirmé':
            # Il biglietto è valido: aggiorna lo stato a Presente
            supabase.table("prenotazioni").update({"stato": "Présent"}).eq("code_qr", code).execute()
            return render_template('scan_result.html', status='success', message=f"Accès autorisé ! Bienvenue {user[0]['nome']}.")
            
        elif stato_attuale == 'Présent':
            # Il biglietto è già stato scansionato in precedenza
            return render_template('scan_result.html', status='error', message=f"Attention : Le billet de {user[0]['nome']} a DÉJÀ ÉTÉ SCANNÉ.")
            
        else:
            # Se è in attesa o sospeso
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