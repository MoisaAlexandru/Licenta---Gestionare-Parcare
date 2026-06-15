import psycopg2

# Link-ul tău direct către Railway
DB_URL = "postgresql://postgres:OdKOjlgrirSObuQVATDxfHQnFShyWpQh@thomas.proxy.rlwy.net:38842/railway"

print("Se conectează la Railway...")

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("Se creează tabelele...")

    # Tabelul pentru mașinile aflate în parcare
    cur.execute('''
    CREATE TABLE IF NOT EXISTS parcare_curenta (
        numar VARCHAR(20) PRIMARY KEY,
        tip VARCHAR(20),
        ora_intrare TIMESTAMP,
        status_plata INTEGER DEFAULT 0,
        ora_limita_iesire TIMESTAMP
    )
    ''')

    # Tabelul pentru abonați
    cur.execute('''
    CREATE TABLE IF NOT EXISTS autorizati (
        numar VARCHAR(20) PRIMARY KEY,
        nume_proprietar VARCHAR(100),
        data_expirare DATE
    )
    ''')

    # Tabelul pentru istoric trafic live
    cur.execute('''
    CREATE TABLE IF NOT EXISTS istoric (
        id SERIAL PRIMARY KEY,
        numar VARCHAR(20),
        actiune VARCHAR(100),
        data_ora TIMESTAMP
    )
    ''')

    conn.commit()
    cur.close()
    conn.close()
    print("SUCCES! Baza de date din Cloud a fost inițializată și este gata de utilizare!")

except Exception as e:
    print(f"A apărut o eroare: {e}")