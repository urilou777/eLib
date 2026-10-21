import sqlite3

def run_enrichment():
    conn = sqlite3.connect('data/librairie.db')
    c = conn.cursor()

    # 1. Ensure dropdown_options contains necessary publishers and categories
    existing_publishers = [r[0] for r in c.execute("SELECT label FROM dropdown_options WHERE group_key = 'publisher'").fetchall()]
    new_publishers = [
        'Bibli\'O',
        'Editheos',
        'Éditions LLB',
        'Mattyson Media',
        'Ministère Multilingue',
        'Mission Esdras Éditions',
        'Independently published'
    ]
    for pub in new_publishers:
        if pub not in existing_publishers:
            c.execute("INSERT INTO dropdown_options (group_key, label) VALUES ('publisher', ?)", (pub,))
            print(f"Added publisher option: {pub}")

    # Fix typo in dropdown option if present: 'Metenoia & Vie' -> 'Metanoia & Vie'
    c.execute("UPDATE dropdown_options SET label = 'Metanoia & Vie' WHERE label = 'Metenoia & Vie'")

    # 2. Update specific books
    updates = [
        # Book 5: 4 secrets d'un mariage réussi
        (5, {
            'author': 'Yvan Castanou',
            'publisher': 'Metanoia & Vie',
            'series': "4 secrets d'un mariage réussi"
        }),
        # Book 8: Choisir le bon conjoint
        (8, {
            'author': 'Yvan Castanou',
            'publisher': 'Metanoia & Vie'
        }),
        # Book 9: Construire un mariage heureux et durable
        (9, {
            'author': 'Yvan Castanou',
            'publisher': 'Metanoia & Vie'
        }),
        # Book 10: Couronnés de succès
        (10, {
            'author': 'Christian Saboukoulou'
        }),
        # Book 11: 3 Clés maîtresses pour parvenir au sommet et briller (typo fix 'somme' -> 'sommet')
        (11, {
            'title': '3 Clés maîtresses pour parvenir au sommet et briller'
        }),
        # Book 16: Il est temps que je rachète le TEMPS (add volume 3)
        (16, {
            'volume': '3'
        }),
        # Book 17: Il est temps que ma vie soit PRODUCTIVE (add volume 2)
        (17, {
            'volume': '2'
        }),
        # Book 22: La prière de l'épouse
        (22, {
            'author': 'Samuel Kamuanga',
            'publisher': 'Independently published'
        }),
        # Book 24: La puissance de la vision
        (24, {
            'author': 'Juliana Ondo',
            'publisher': 'Metanoia & Vie',
            'volume': '1'
        }),
        # Book 25: La puissance d'une jeunesse choisie et révélée par Dieu
        (25, {
            'title': "La puissance d'une jeunesse choisie et révélée par Dieu",
            'author': 'Ghislain Biabatantou',
            'publisher': 'BGR EDITION'
        }),
        # Book 26: L'art de communiquer
        (26, {
            'author': 'José Biabatantou',
            'publisher': 'BGR EDITION'
        }),
        # Book 27: L'onction de l'épouse
        (27, {
            'author': 'Samuel Kamuanga',
            'publisher': 'Independently published'
        }),
        # Book 30: Mon héritage
        (30, {
            'author': 'Ghislain Biabatantou'
        }),
        # Book 31: Naître dans le Royaume (Ado)
        (31, {
            'author': 'Myriam Didi Kouko',
            'publisher': 'Les Vertueux Collection',
            'category': 'Enfant'
        }),
        # Book 32: Naître dans le Royaume (Junior)
        (32, {
            'author': 'Myriam Didi Kouko',
            'publisher': 'Les Vertueux Collection',
            'category': 'Enfant'
        }),
        # Book 34: Restaurer l'âme blessée
        (34, {
            'author': 'José Biabatantou',
            'publisher': 'BGR EDITION'
        }),
        # Book 35: Revêtu de puissance
        (35, {
            'author': 'Job Mukadi',
            'publisher': 'Metanoia & Vie'
        }),
        # Book 37: Sortir des Prisons intérieur (typo fix 'intérieur' -> 'intérieures')
        (37, {
            'title': 'Sortir des prisons intérieures'
        }),
        # Book 38: La puissance de la dîme
        (38, {
            'publisher': 'Mattyson Media',
            'type': 'Souple'
        }),
        # Book 42: La Sainte Bible de poche (zippée)
        (42, {
            'publisher': "Bibli'O",
            'type': 'Rigide'
        }),
        # Book 43: Bible Segond 1880 révisée compacte noire couverture rigide
        (43, {
            'title': 'Bible Segond 1880 révisée compacte noire couverture rigide',
            'publisher': 'Ésaïe 55'
        }),
        # Book 47: La Bible en 1 an (sans deutérocanoniques)
        (47, {
            'title': 'La Bible en 1 an (sans deutérocanoniques)',
            'publisher': "Bibli'O"
        }),
        # Book 48: La Bible femmes à son écoute
        (48, {
            'publisher': 'Ministère Multilingue'
        }),
        # Book 49: Le dessein de Dieu pour l'identité féminine
        (49, {
            'author': 'Myles Munroe',
            'publisher': 'Mission Esdras Éditions',
            'category': 'Standard',
            'price': 24.0
        }),
        # Book 50: L'évangile en bandes dessinées
        (50, {
            'author': 'Iva Hoth & André Le Blanc',
            'publisher': 'Éditions LLB',
            'category': 'Enfant',
            'type': 'Souple'
        }),
        # Book 51: Vivre et apprécier son célibat
        (51, {
            'author': 'Jacques Mbalanda',
            'publisher': 'Editheos',
            'category': 'Standard',
            'type': 'Souple',
            'price': 15.0
        }),
        # Book 52: Une seule décision peut tout changer
        (52, {
            'author': 'José Biabatantou',
            'publisher': 'Editheos',
            'category': 'Standard',
            'type': 'Souple'
        }),
        # Book 53: Noah comprend l'importance de la prière
        (53, {
            'author': 'Oly P.',
            'publisher': 'Independently published',
            'category': 'Enfant',
            'type': 'Souple',
            'price': 11.9
        }),
        # Book 54: Bible Segond 1880 révisée compacte duo bleu nuit / ciel
        (54, {
            'title': 'Bible Segond 1880 révisée compacte duo bleu nuit / ciel',
            'publisher': 'Ésaïe 55',
            'type': 'Souple'
        }),
        # Book 55: Bible Segond 1880 révisée compacte rouge bordeaux couverture rigide
        (55, {
            'title': 'Bible Segond 1880 révisée compacte rouge bordeaux couverture rigide',
            'publisher': 'Ésaïe 55'
        }),
        # Book 56: Kéren apprend à ne plus cacher ses bêtises
        (56, {
            'author': 'Oly P.',
            'publisher': 'Independently published',
            'category': 'Enfant',
            'type': 'Souple',
            'price': 11.9
        })
    ]

    for book_id, fields in updates:
        set_clauses = [f"{k} = ?" for k in fields.keys()]
        values = list(fields.values()) + [book_id]
        query = f"UPDATE books SET {', '.join(set_clauses)} WHERE id = ?"
        c.execute(query, values)
        print(f"Updated book ID {book_id}: {fields}")

    # Also add 'Ésaïe 55' to dropdown_options if not present
    c.execute("INSERT OR IGNORE INTO dropdown_options (group_key, label) VALUES ('publisher', 'Ésaïe 55')")

    conn.commit()
    conn.close()
    print("Database enrichment complete!")

if __name__ == '__main__':
    run_enrichment()
