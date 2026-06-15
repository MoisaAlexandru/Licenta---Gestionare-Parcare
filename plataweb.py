import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime, timedelta
import re
import math

app = Flask(__name__)

# Funcție de conectare adaptată pentru PostgreSQL
def get_db_connection():
    # Railway injectează automat DATABASE_URL
    conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    return conn

# Funcție pentru a obține un cursor care returnează datele ca dicționare
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
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # Am adăugat "AS total" pentru a avea o cheie clară
    cur.execute("SELECT COUNT(*) as total FROM parcare_curenta")
    result = cur.fetchone()
    # Accesăm prin cheia 'total'
    ocupate = result['total'] if result else 0
    cur.close()
    conn.close()
    return max(0, CAPACITATE_MAXIMA - ocupate)

# ==========================================
# RUTE CLIENT
# ==========================================
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
            suma_datorata = ore_state * 5
            if stare_parcare['status_plata'] == 1:
                limita = datetime.strptime(str(stare_parcare['ora_limita_iesire']), '%Y-%m-%d %H:%M:%S')
                if acum <= limita:
                    return render_template('checkout.html', numar=numar, nume="Vizitator", status="Status: PLĂTIT.", clasa="text-success", suma_plata=0)
            return render_template('checkout.html', numar=numar, nume="Vizitator", status=f"Timp: {ore_state} ore. Tarif: {suma_datorata} RON.", clasa="text-danger", suma_plata=suma_datorata)

    if masina_abonament:
        data_exp = datetime.strptime(str(masina_abonament['data_expirare']), '%Y-%m-%d')
        status_text = f"Abonament {'VALID' if data_exp >= datetime.now() else 'EXPIRAT'}. Mașina nu este în parcare."
        return render_template('checkout.html', numar=numar, nume=masina_abonament['nume_proprietar'], status=status_text, clasa="text-success" if data_exp >= datetime.now() else "text-danger")

    return render_template('index.html', mesaj="Mașină negăsită.", clasa="alert-warning", locuri_libere=locuri_libere, numar_incercat=numar)

@app.route('/plateste', methods=['POST'])
def plateste():
    numar = request.form.get('numar', '').strip().upper()
    luni = request.form.get('luni')
    conn, cur = get_db_cursor()
    acum = datetime.now()
    
    if luni:
        luni_int = int(luni)
        cur.execute("SELECT data_expirare FROM autorizati WHERE numar = %s", (numar,))
        abonat = cur.fetchone()
        data_exp = datetime.strptime(str(abonat['data_expirare']), '%Y-%m-%d') if abonat else acum
        noua_data = (max(data_exp, acum) + timedelta(days=luni_int*30)).strftime('%Y-%m-%d')
        cur.execute("UPDATE autorizati SET data_expirare = %s WHERE numar = %s", (noua_data, numar))
        cur.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (%s, %s, %s)", (numar, f"PRELUNGIRE {luni_int} LUNI", acum))
    else:
        ora_limita = (acum + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
        cur.execute('UPDATE parcare_curenta SET status_plata = 1, ora_limita_iesire = %s WHERE numar = %s', (ora_limita, numar))
        cur.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (%s, 'PLATA EFECTUATA', %s)", (numar, acum))
    
    conn.commit()
    conn.close()
    return render_template('index.html', mesaj="Operațiune efectuată cu succes!", clasa="alert-success", locuri_libere=preia_locuri_libere())

@app.route('/inregistrare_noua', methods=['POST'])
def inregistrare_noua():
    numar = request.form.get('numar', '').strip().upper().replace(" ", "")
    nume = request.form.get('nume', '').strip()
    luni = int(request.form.get('luni', 1))
    data_exp = (datetime.now() + timedelta(days=luni*30)).strftime('%Y-%m-%d')
    
    conn, cur = get_db_cursor()
    # Postgres foloseste ON CONFLICT pentru a inlocui INSERT OR REPLACE
    cur.execute("""INSERT INTO autorizati (numar, nume_proprietar, data_expirare) VALUES (%s, %s, %s)
                   ON CONFLICT (numar) DO UPDATE SET nume_proprietar = EXCLUDED.nume_proprietar, data_expirare = EXCLUDED.data_expirare""", 
                (numar, nume, data_exp))
    conn.commit()
    conn.close()
    return render_template('index.html', mesaj="Abonament înregistrat!", clasa="alert-success", locuri_libere=preia_locuri_libere())

# ==========================================
# RUTE ADMIN
# ==========================================
@app.route('/admin')
def admin_index():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT numar, nume_proprietar, data_expirare FROM autorizati ORDER BY nume_proprietar ASC")
    utilizatori = cur.fetchall()
    
    cur.execute("SELECT numar, actiune, data_ora FROM istoric ORDER BY data_ora DESC LIMIT 50")
    istoric = cur.fetchall()
    
    # Corecția pentru count-uri:
    cur.execute("SELECT COUNT(*) as total FROM autorizati")
    total_autorizati = cur.fetchone()['total']
    
    cur.execute("SELECT COUNT(*) as total FROM istoric")
    total_istoric = cur.fetchone()['total']
    
    cur.close()
    conn.close()
    
    return render_template('admin.html', utilizatori=utilizatori, istoric=istoric, 
                           total_autorizati=total_autorizati, total_istoric=total_istoric)

@app.route('/admin/adauga', methods=['POST'])
def admin_adauga():
    numar = request.form.get('numar', '').strip().upper().replace(" ", "")
    nume = request.form.get('nume', '').strip()
    data_exp = request.form.get('data_exp', '').strip()
    if numar and nume and data_exp:
        conn, cur = get_db_cursor()
        cur.execute("INSERT INTO autorizati (numar, nume_proprietar, data_expirare) VALUES (%s, %s, %s) ON CONFLICT (numar) DO UPDATE SET data_expirare = EXCLUDED.data_expirare", (numar, nume, data_exp))
        conn.commit()
        conn.close()
    return redirect(url_for('admin_index'))

@app.route('/admin/sterge/<numar>', methods=['POST'])
def admin_sterge(numar):
    conn, cur = get_db_cursor()
    cur.execute("DELETE FROM autorizati WHERE numar = %s", (numar,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)