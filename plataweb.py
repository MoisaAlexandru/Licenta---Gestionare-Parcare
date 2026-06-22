import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
import re
import math

app = Flask(__name__)

app.secret_key = 'licenta2026_alexandru' 

TARIF_ORA = 5

def get_db_connection():
    
    return psycopg2.connect(os.environ.get('DATABASE_URL'))

def get_db_cursor():
    conn = get_db_connection()
    return conn, conn.cursor(cursor_factory=RealDictCursor)

def este_numar_valid_romanesc(numar):
    numar = numar.replace(" ", "").upper()
    pattern_std = r"^[A-Z]{1,2}[0-9]{2,3}[A-Z]{3}$"
    pattern_rosu = r"^[A-Z]{1,2}[0-9]{3,6}$"
    return bool(re.match(pattern_std, numar) or re.match(pattern_rosu, numar))

def preia_locuri_libere():
    CAPACITATE_MAXIMA = 50
    try:
        conn, cur = get_db_cursor()
        cur.execute("SELECT COUNT(*) as total FROM parcare_curenta")
        result = cur.fetchone()
        ocupate = result['total'] if result else 0
        cur.close()
        conn.close()
        return max(0, CAPACITATE_MAXIMA - ocupate)
    except:
        return CAPACITATE_MAXIMA


@app.route('/')
def index():
    return render_template('index.html', locuri_libere=preia_locuri_libere())

@app.route('/verifica', methods=['POST'])
def verifica():
    numar = request.form.get('numar', '').strip().upper().replace(" ", "")
    locuri_libere = preia_locuri_libere()
    
    if not este_numar_valid_romanesc(numar):
        return render_template('index.html', mesaj="Format INVALID!", clasa="alert-danger", locuri_libere=locuri_libere, numar_incercat=numar)

    conn, cur = get_db_cursor()
    cur.execute('SELECT * FROM parcare_curenta WHERE numar = %s', (numar,))
    stare_parcare = cur.fetchone()
    cur.execute('SELECT * FROM autorizati WHERE numar = %s', (numar,))
    masina_abonament = cur.fetchone()
    conn.close()

    # CAZUL 1: MAȘINA ESTE FIZIC ÎN PARCARE ACUM
    if stare_parcare:
        if stare_parcare['tip'] == 'ABONAMENT':
            status_text = "Status: ÎN PARCARE (ABONAT). Ieșirea este gratuită."
            nume_afisat = masina_abonament['nume_proprietar'] if masina_abonament else "Abonat"
            return render_template('checkout.html', numar=numar, nume=nume_afisat, status=status_text, clasa="text-success", suma_plata=0)
        else:
            ora_intrare = datetime.strptime(str(stare_parcare['ora_intrare']), '%Y-%m-%d %H:%M:%S')
            acum = datetime.now()
            diferenta = acum - ora_intrare
            
            ore_state = math.ceil(diferenta.total_seconds() / 3600)
            if ore_state == 0: ore_state = 1
            suma_datorata = ore_state * TARIF_ORA

            if stare_parcare['status_plata'] == 1:
                limita = datetime.strptime(str(stare_parcare['ora_limita_iesire']), '%Y-%m-%d %H:%M:%S')
                if acum <= limita:
                    return render_template('checkout.html', numar=numar, nume="Vizitator", status="Status: PLĂTIT. Aveți timp să părăsiți parcarea.", clasa="text-success", suma_plata=0)

            status_text = f"Timp petrecut: {ore_state} ore. Tarif: {TARIF_ORA} RON/oră."
            return render_template('checkout.html', numar=numar, nume="Vizitator", status=status_text, clasa="text-danger", suma_plata=suma_datorata)

    # CAZUL 2: MAȘINA NU E ÎN PARCARE, DAR ARE ABONAMENT
    if masina_abonament:
        data_exp = datetime.strptime(str(masina_abonament['data_expirare']), '%Y-%m-%d')
        acum = datetime.now()
        
        if data_exp < acum:
            status_text = f"Abonament EXPIRAT (la {masina_abonament['data_expirare']}). Mașina nu este în parcare."
            clasa_css = "text-danger"
        else:
            status_text = f"Abonament VALID (până la {masina_abonament['data_expirare']}). Mașina nu este în parcare."
            clasa_css = "text-success"

        return render_template('checkout.html', numar=numar, nume=masina_abonament['nume_proprietar'], status=status_text, clasa=clasa_css)

    # CAZUL 3: MAȘINA NU E ÎN PARCARE ȘI E NECUNOSCUTĂ
    return render_template('index.html', 
                           mesaj="Această mașină nu se află în parcare și nu figurează în baza de clienți.", 
                           clasa="alert-warning", locuri_libere=locuri_libere, numar_incercat=numar)

@app.route('/plateste', methods=['POST'])
def plateste():
    numar = request.form.get('numar', '').strip().upper()
    luni = request.form.get('luni')
    
    acum = datetime.now()
    acum_str = acum.strftime('%Y-%m-%d %H:%M:%S')
    
    conn, cur = get_db_cursor()
    
    # SCENARIUL 1: ESTE O PRELUNGIRE DE ABONAMENT
    if luni:
        try:
            luni_int = int(luni)
        except ValueError:
            luni_int = 1
            
        cur.execute("SELECT data_expirare FROM autorizati WHERE numar = %s", (numar,))
        abonat = cur.fetchone()
        
        if abonat:
            data_exp_curenta = datetime.strptime(str(abonat['data_expirare']), '%Y-%m-%d')
            
            if data_exp_curenta > acum:
                noua_data_exp = (data_exp_curenta + timedelta(days=luni_int*30)).strftime('%Y-%m-%d')
            else:
                noua_data_exp = (acum + timedelta(days=luni_int*30)).strftime('%Y-%m-%d')
            
            text_luni = "LUNĂ" if luni_int == 1 else "LUNI"
            
            cur.execute("UPDATE autorizati SET data_expirare = %s WHERE numar = %s", (noua_data_exp, numar))
            cur.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (%s, %s, %s)",
                         (numar, f"PRELUNGIRE ABONAMENT ({luni_int} {text_luni})", acum_str))
            
            mesaj = f"Abonament prelungit cu succes! Noua dată de expirare pentru {numar} este {noua_data_exp}."
            clasa = "alert-success"
            
    # SCENARIUL 2: ESTE PLATA PE ORĂ (VIZITATOR)
    else:
        ora_limita = (acum + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
        
        cur.execute('UPDATE parcare_curenta SET status_plata = 1, ora_limita_iesire = %s WHERE numar = %s', (ora_limita, numar))
        cur.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (%s, 'PLATA EFECTUATA (5 MIN VALABILITATE)', %s)",
                     (numar, acum_str))
        
        mesaj = "Plata a fost efectuată cu succes! Aveți 5 minute la dispoziție pentru a părăsi parcarea."
        clasa = "alert-success"

    conn.commit()
    conn.close()
    
    return render_template('index.html', mesaj=mesaj, clasa=clasa, locuri_libere=preia_locuri_libere())

@app.route('/inregistrare_noua', methods=['POST'])
def inregistrare_noua():
    numar = request.form.get('numar', '').strip().upper().replace(" ", "")
    nume = request.form.get('nume', '').strip()
    
    try:
        luni = int(request.form.get('luni'))
    except (ValueError, TypeError):
        luni = 1
        
    zile_valabilitate = luni * 30
    data_expirare = (datetime.now() + timedelta(days=zile_valabilitate)).strftime('%Y-%m-%d')
    acum_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn, cur = get_db_cursor()
    try:
        cur.execute("""INSERT INTO autorizati (numar, nume_proprietar, data_expirare) VALUES (%s, %s, %s)
                       ON CONFLICT (numar) DO UPDATE SET nume_proprietar = EXCLUDED.nume_proprietar, data_expirare = EXCLUDED.data_expirare""", 
                    (numar, nume, data_expirare))
                     
        text_luni = "LUNĂ" if luni == 1 else "LUNI"
        actiune_log = f"ABONAMENT NOU CREAT ({luni} {text_luni})"
        
        cur.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (%s, %s, %s)",
                     (numar, actiune_log, acum_str))
        conn.commit()
        
        mesaj_succes = f"Felicitări! Abonamentul pentru {numar} a fost creat cu succes. Valabil până la: {data_expirare}."
        clasa_succes = "alert-success"
    except Exception as e:
        mesaj_succes = f"Eroare la salvarea în baza de date: {e}"
        clasa_succes = "alert-danger"
    finally:
        conn.close()
        
    return render_template('index.html', mesaj=mesaj_succes, clasa=clasa_succes, locuri_libere=preia_locuri_libere())

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    # Login check
    if request.method == 'POST':
        if request.form.get('password') == 'parola123': # PAROLA DE ADMIN AICI
            session['admin_logged'] = True
            return redirect(url_for('admin'))
        else:
            return "Parolă incorectă! <a href='/admin'>Înapoi</a>"
            
    if not session.get('admin_logged'):
        return '''
        <div style="display:flex; justify-content:center; align-items:center; height:100vh; background:#f4f7f6;">
            <form method="post" style="background:white; padding:2rem; border-radius:10px; box-shadow:0 4px 6px rgba(0,0,0,0.1); width: 300px; text-align: center;">
                <h3 style="margin-bottom: 20px; font-family: sans-serif;">Acces Admin</h3>
                <input type="password" name="password" placeholder="Introdu parola" required style="padding:10px; margin-bottom:15px; width:100%; border: 1px solid #ccc; border-radius: 5px;">
                <button type="submit" style="background:#003d73; color:white; border:none; padding:10px; width:100%; cursor:pointer; border-radius: 5px; font-weight: bold;">Login</button>
            </form>
        </div>
        '''

    conn, cur = get_db_cursor()
    
    # 1. Preluăm abonații
    cur.execute("SELECT numar, nume_proprietar, data_expirare FROM autorizati ORDER BY nume_proprietar ASC")
    utilizatori = cur.fetchall()
    
    # 2. Preluăm istoricul recent
    cur.execute("SELECT numar, actiune, data_ora FROM istoric ORDER BY data_ora DESC LIMIT 50")
    istoric = cur.fetchall()
    
    # 3. Preluăm mașinile CURENTE din parcare și calculăm costurile
    cur.execute("SELECT numar, ora_intrare, tip, status_plata FROM parcare_curenta ORDER BY ora_intrare DESC")
    masini_parcare = cur.fetchall()
    
    parcare_live = []
    acum = datetime.now()
    
    for masina in masini_parcare:
        ora_intrare = datetime.strptime(str(masina['ora_intrare']), '%Y-%m-%d %H:%M:%S')
        diferenta = acum - ora_intrare
        minute_totale = int(diferenta.total_seconds() / 60)
        ore = minute_totale // 60
        minute = minute_totale % 60
        timp_formatat = f"{ore}h {minute}m"
        
        cost_curent = 0
        if masina['tip'] == 'VIZITATOR':
            ore_state = math.ceil(diferenta.total_seconds() / 3600)
            if ore_state == 0: ore_state = 1
            cost_curent = ore_state * TARIF_ORA
            
        parcare_live.append({
            'numar': masina['numar'],
            'ora_intrare': masina['ora_intrare'],
            'tip': masina['tip'],
            'status_plata': masina['status_plata'],
            'timp_petrecut': timp_formatat,
            'cost_curent': cost_curent
        })
    
    # Statistici rapide
    cur.execute("SELECT COUNT(*) as total FROM autorizati")
    total_autorizati = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) as total FROM istoric")
    total_istoric = cur.fetchone()['total']
    conn.close()
    
    astazi = datetime.now().strftime('%Y-%m-%d')
    
    return render_template(
        'admin.html',
        utilizatori=utilizatori,
        istoric=istoric,
        parcare_live=parcare_live,  # Am adăugat noua variabilă aici
        total_autorizati=total_autorizati,
        total_istoric=total_istoric,
        astazi=astazi
    )

@app.route('/admin/adauga', methods=['POST'])
def admin_adauga():
    if not session.get('admin_logged'):
        return redirect(url_for('admin'))
        
    numar = request.form.get('numar', '').strip().upper().replace(" ", "")
    nume = request.form.get('nume', '').strip()
    data_exp = request.form.get('data_exp', '').strip()

    if numar and nume and data_exp:
        conn, cur = get_db_cursor()
        cur.execute("""INSERT INTO autorizati (numar, nume_proprietar, data_expirare) VALUES (%s, %s, %s) 
                       ON CONFLICT (numar) DO UPDATE SET data_expirare = EXCLUDED.data_expirare, nume_proprietar = EXCLUDED.nume_proprietar""", 
                    (numar, nume, data_exp))
        conn.commit()
        conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/sterge/<numar>', methods=['POST'])
def admin_sterge(numar):
    if not session.get('admin_logged'):
        return redirect(url_for('admin'))
        
    conn, cur = get_db_cursor()
    cur.execute("DELETE FROM autorizati WHERE numar = %s", (numar,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)