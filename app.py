import os
import secrets
import qrcode
from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client, Client

# Initialisation Supabase
url: str = "https://nujvctqiggtxyeewvexu.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im51anZjdHFpZ2d0eHllZXd2ZXh1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTI5OTE3NCwiZXhwIjoyMDk0ODc1MTc0fQ.nwJXQxvj8YNWjZnEoWd0len471k2sjJa2BlUfGxDk6U"
supabase: Client = create_client(url, key)

app = Flask(__name__)
app.secret_key = 'wecadi_prestige_key_2026'

os.makedirs('static/qrcodes', exist_ok=True)
ADMIN_PASSWORD = 'wecadi2026'

# ----------------- ROTTE PUBBLICHE ----------------- #

@app.route('/', methods=['GET', 'POST'])
def home():
    success = False 
    if request.method == 'POST':
        supabase.table("prenotazioni").insert({
            "nome": request.form.get('nome'),
            "email": request.form.get('email'),
            "telefono": request.form.get('telefono'),
            "stato": "In attesa"
        }).execute()
        success = True 
    return render_template('index.html', success=success)

@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login_user.html')

@app.route('/login_user', methods=['POST'])
def login_user():
    email = request.form.get('email')
    telefono = request.form.get('telefono')
    
    # Optimisation : Sélectionnez uniquement les champs nécessaires
    # et utilisez un filtre strict
    try:
        response = supabase.table("prenotazioni")\
            .select("id, email, telefono")\
            .eq("email", email)\
            .eq("telefono", telefono)\
            .limit(1)\
            .execute()
        
        if response.data:
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
    if 'user_id' not in session: return redirect(url_for('login_page'))
    user_data = supabase.table("prenotazioni").select("*").eq("id", session['user_id']).execute().data[0]
    return render_template('user_dashboard.html', user=list(user_data.values()))

@app.route('/logout')
def logout():
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
    
    # Calcul des stats côté application pour plus de simplicité
    stats = {
        'total': len(data),
        'confirmes': len([p for p in data if p['stato'] == 'Confirmé']),
        'en_attente': len([p for p in data if p['stato'] == 'In attesa']),
        'presents': len([p for p in data if p['stato'] == 'Présent'])
    }
    
    query = request.args.get('q', '').lower()
    if query:
        data = [p for p in data if query in str(p['nome']).lower() or query in str(p['email']).lower() or query in str(p['code_qr'] or '').lower()]
    
    # Conversion des dictionnaires Supabase en listes pour votre template existant
    prenotazioni = [[p['id'], p['nome'], p['email'], p['telefono'], p['stato'], p.get('code_qr')] for p in data]
    
    return render_template('admin_dashboard.html', prenotazioni=prenotazioni, stats=stats, search_query=query)

@app.route('/admin/valider/<int:id>')
def admin_valider(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    
    nuovo_code = secrets.token_hex(3).upper()
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(nuovo_code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(f"static/qrcodes/qr_{id}.png")

    supabase.table("prenotazioni").update({"stato": "Confirmé", "code_qr": nuovo_code}).eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/scan_manual/<code>')
def scan_manual(code):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    
    user = supabase.table("prenotazioni").select("*").eq("code_qr", code).execute().data
    
    if user:
        if user[0]['stato'] == 'Confirmé':
            supabase.table("prenotazioni").update({"stato": "Présent"}).eq("code_qr", code).execute()
            return render_template('scan_result.html', status='success', message=f"Bienvenue {user[0]['nome']} !")
        return render_template('scan_result.html', status='error', message="Billet non confirmé.")
    return render_template('scan_result.html', status='error', message="Code invalide.")

@app.route('/admin/suspendre/<int:id>')
def admin_suspendre(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    if os.path.exists(f"static/qrcodes/qr_{id}.png"): os.remove(f"static/qrcodes/qr_{id}.png")
    supabase.table("prenotazioni").update({"stato": "Suspendu"}).eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/supprimer/<int:id>')
def admin_supprimer(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_page'))
    if os.path.exists(f"static/qrcodes/qr_{id}.png"): os.remove(f"static/qrcodes/qr_{id}.png")
    supabase.table("prenotazioni").delete().eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_page'))

if __name__ == '__main__':
    app.run(debug=True)