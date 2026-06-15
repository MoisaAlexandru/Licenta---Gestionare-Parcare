import sqlite3
from datetime import datetime, timedelta

def actualizeaza_baza_de_date():
    print("--- ACTUALIZARE BAZA DE DATE CU NUMERE NOI ---")
    
    conn = sqlite3.connect('parcare.db')
    cursor = conn.cursor()
    
    # 1. Ne asigurăm că tabelele există
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS autorizati (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nume_proprietar TEXT,
            numar TEXT,
            data_expirare TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS istoric (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numar TEXT,
            actiune TEXT,
            data_ora TEXT
        )
    ''')

    # 2. Calculăm datele dinamic (ca să fie valabile oricând rulezi scriptul)
    azi = datetime.now()
    valid = (azi + timedelta(days=365)).strftime("%Y-%m-%d") # Valabil 1 an de azi
    expirat = (azi - timedelta(days=1)).strftime("%Y-%m-%d") # Expirat ieri

    # 3. LISTA TA ACTUALIZATĂ
    utilizatori_de_verificat = [
        ('Student Licenta',      'VS16CCG', valid),
        ('Profesor Coordonator', 'IS15SXO', valid),
        ('Vizitator Expirat',    'B114PGT', expirat),
        ('Test SB',              'SB07XXN', valid),
        ('Moisa',              'IS18ZAR', valid)
    ]

    contor_noi = 0
    contor_existenti = 0

    # 4. Verificăm și inserăm
    for nume, nr_inmatriculare, data_exp in utilizatori_de_verificat:
        
        # Căutăm dacă numărul există deja
        cursor.execute("SELECT id FROM autorizati WHERE numar = ?", (nr_inmatriculare,))
        rezultat = cursor.fetchone()

        if rezultat is None:
            # NU există -> Îl adăugăm
            cursor.execute('INSERT INTO autorizati (nume_proprietar, numar, data_expirare) VALUES (?, ?, ?)', 
                           (nume, nr_inmatriculare, data_exp))
            print(f"[NOU] Am adăugat: {nr_inmatriculare} ({nume}) - {data_exp}")
            contor_noi += 1
        else:
            # EXISTĂ -> Nu îl dublăm
            print(f"[SKIP] {nr_inmatriculare} este deja în bază.")
            contor_existenti += 1

    conn.commit()
    conn.close()
    
    print("-" * 30)
    print(f"GATA: {contor_noi} utilizatori adăugați, {contor_existenti} deja existau.")

if __name__ == "__main__":
    actualizeaza_baza_de_date()