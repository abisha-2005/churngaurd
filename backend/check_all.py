import sqlite3
conn = sqlite3.connect('storage/app.db')
cur = conn.cursor()
cur.execute("SELECT id, filename, status FROM analyses ORDER BY id;")
for row in cur.fetchall():
    print(row)
