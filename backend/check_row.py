import sqlite3
conn = sqlite3.connect('storage/app.db')
cur = conn.cursor()

cur.execute("PRAGMA table_info(analyses);")
print("Columns:")
for col in cur.fetchall():
    print(col)

print()
cur.execute("SELECT * FROM analyses WHERE id=12;")
row = cur.fetchone()
col_names = [d[0] for d in cur.description]
print("Row 12:")
for name, val in zip(col_names, row):
    print(f"  {name}: {val}")
