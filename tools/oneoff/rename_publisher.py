import sqlite3

OLD = 'Independently published'
NEW = 'Publication indépendante'

conn = sqlite3.connect('data/librairie.db')
c = conn.cursor()
b = c.execute("UPDATE books SET publisher = ? WHERE publisher = ?", (NEW, OLD)).rowcount
d = c.execute("UPDATE dropdown_options SET label = ? WHERE group_key = 'publisher' AND label = ?", (NEW, OLD)).rowcount
conn.commit()
print(f"books updated: {b}, dropdown options updated: {d}")
print(c.execute("SELECT id, title, publisher FROM books WHERE publisher = ?", (NEW,)).fetchall())
conn.close()
