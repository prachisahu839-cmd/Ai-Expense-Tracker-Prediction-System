import sqlite3

conn = sqlite3.connect("database.db")
cur = conn.cursor()

cur.execute("ALTER TABLE users ADD COLUMN budget REAL DEFAULT 0")

conn.commit()
conn.close()

print("Column added successfully")