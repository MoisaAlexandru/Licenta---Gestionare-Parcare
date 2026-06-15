import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
import re
import math

app = Flask(__name__)
app.secret_key = 'o_cheie_secreta_licenta' # Schimbă cu ceva unic

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
    conn, cur = get_db_cursor()
    cur.execute("SELECT COUNT(*) as total FROM parcare_curenta")
    ocupate = cur.fetchone()['total']
    conn.close()
    return max(0, 50 - ocupate)

@app.route('/')
def index():
    return render_template('index.html', locuri_libere=preia_locuri_libere())

@app.route('/verifica', methods=['POST'])
def verifica():
    numar = request.form.get('numar', '').strip().upper().replace(" ", "")
    if not este_numar_valid_romanesc(numar):
        return render_template('index.html', mesaj="Format INVALID!", clasa="alert-danger", locuri_libere=preia_locuri_libere())

    conn, cur = get_db_cursor()
    cur.execute('SELECT * FROM parcare_curenta WHERE numar = %s', (numar,))
    stare_parcare = cur.fetchone()
    cur.execute('SELECT * FROM autorizati WHERE numar = %s', (numar,))
    masina_abonament = cur.fetchone()
    conn.close()

    if stare_parcare:
        # Aici ar trebui să ai un template 'checkout.html' sau să redirecționezi
        return "Masina este in parcare - adauga aici logica de checkout" 

    if masina_abonament:
        data_exp = datetime.strptime(str(masina_abonament['data_expirare']), '%Y-%m-%d')
        status = "VALID" if data_exp >= datetime.now() else "EXPIRAT"
        return render_template('index.html', mesaj=f"Abonament {status} pentru {numar}", clasa="text-success" if status=="VALID" else "text-danger", locuri_libere=preia_locuri_libere())

    return render_template('index.html', mesaj="Mașină negăsită. Aceasta nu figurează în baza de date.", clasa="alert-warning", numar_incercat=numar, locuri_libere=preia_locuri_libere())

@app.route('/plateste', methods=['POST'])
def plateste():
    numar = request.form.get('numar', '').strip().upper()
    luni = request.form.get('luni')
    conn, cur = get_db_cursor()
    
    if luni: # Prelungire abonament
        cur.execute("SELECT data_expirare FROM autorizati WHERE numar = %s", (numar,))
        abonat = cur.fetchone()
        data_exp = datetime.strptime(str(abonat['data_expirare']), '%Y-%m-%d') if abonat else datetime.now()
        noua_data = (max(data_exp, datetime.now()) + timedelta(days=int(luni)*30)).strftime('%Y-%m-%d')
        cur.execute("UPDATE autorizati SET data_expirare = %s WHERE numar = %s", (noua_data, numar))
    else: # Plata ora vizitator
        cur.execute('UPDATE parcare_curenta SET status_plata = 1, ora_limita_iesire = %s WHERE numar = %s', 
                    ((datetime.now() + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S'), numar))
    
    conn.commit()
    conn.close()
    return render_template('index.html', mesaj="Operațiune efectuată!", clasa="alert-success", locuri_libere=preia_locuri_libere())

@app.route('/inregistrare_noua', methods=['POST'])
def inregistrare_noua():
    numar = request.form.get('numar', '').strip().upper()
    nume = request.form.get('nume', '').strip()
    luni = int(request.form.get('luni', 1))
    data_exp = (datetime.now() + timedelta(days=luni*30)).strftime('%Y-%m-%d')
    
    conn, cur = get_db_cursor()
    cur.execute("INSERT INTO autorizati (numar, nume_proprietar, data_expirare) VALUES (%s, %s, %s) ON CONFLICT (numar) DO UPDATE SET nume_proprietar = EXCLUDED.nume_proprietar, data_expirare = EXCLUDED.data_expirare", (numar, nume, data_exp))
    conn.commit()
    conn.close()
    return render_template('index.html', mesaj="Abonament înregistrat cu succes!", clasa="alert-success", locuri_libere=preia_locuri_libere())

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST' and request.form.get('password') == 'licentaproiect':
        session['admin'] = True
        return redirect(url_for('admin_index'))
    if session.get('admin'):
        return admin_index()
    return '<form method="post"><input type="password" name="password"><button type="submit">Login</button></form>'

def admin_index():
    conn, cur = get_db_cursor()
    cur.execute("SELECT numar, nume_proprietar, data_expirare FROM autorizati")
    utilizatori = cur.fetchall()
    conn.close()
    return render_template('admin.html', utilizatori=utilizatori)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)