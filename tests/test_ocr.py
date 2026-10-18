import asyncio
import base64
import json
import os
import sys
import unittest
import numpy as np
import cv2
from starlette.requests import Request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.main import ocr_scan
from app.ocr import (
    extract_isbn,
    extract_price,
    scan_book_page,
    format_sentence_case,
    format_author_name,
    match_author_in_database,
    match_publisher_in_database,
)


class TestOcr(unittest.TestCase):
    def test_heuristics_isbn(self):
        self.assertEqual(extract_isbn("ISBN 978-2-87907-727-7"), "9782879077277")
        self.assertEqual(extract_isbn("9782914563878"), "9782914563878")
        self.assertEqual(extract_isbn("ISBN-10: 2-87907-727-X"), "287907727X")
        self.assertIsNone(extract_isbn("Aucun numero ici"))

    def test_heuristics_price(self):
        self.assertEqual(extract_price("Prix : 18,50 € TTC"), 18.5)
        self.assertEqual(extract_price("15€"), 15.0)
        self.assertIsNone(extract_price("Pas de prix"))

    def test_casing_rules(self):
        # Sentence case strict : 1ère lettre majuscule, reste minuscules
        self.assertEqual(format_sentence_case("LE COMBAT SPIRITUEL"), "Le combat spirituel")
        self.assertEqual(
            format_sentence_case("ESTHER L'ÉPOUSE RÉVÉLÉE : PAR LA TENTATIVE DE GÉNOCIDE"),
            "Esther l'épouse révélée : Par la tentative de génocide"
        )
        # Nom et prénom de l'auteur capitalisés
        self.assertEqual(format_author_name("yvan castanou"), "Yvan Castanou")
        self.assertEqual(format_author_name("modestine castanou"), "Modestine Castanou")
        self.assertEqual(format_author_name("jean-marc thobois"), "Jean-Marc Thobois")

    def test_author_db_strict_matching_and_typos(self):
        db_authors = ["Yvan Castanou", "Modestine Castanou", "Marcello Tunasi", "Ghislain Biabatantou"]
        # Modestine doit matcher Modestine, pas Yvan
        self.assertEqual(
            match_author_in_database("Esther l'épouse révélée Modestine Castanou", "Modestine Castanou", db_authors),
            "Modestine Castanou"
        )
        # Tolérance aux fautes d'orthographe (ex: Modestlne -> Modestine)
        self.assertEqual(
            match_author_in_database("Esther par Modestlne Castanou", "Modestlne Castanou", db_authors),
            "Modestine Castanou"
        )
        # Marcello Tunassi -> Marcello Tunasi
        self.assertEqual(
            match_author_in_database("Livre par Marcello Tunassi", "Marcello Tunassi", db_authors),
            "Marcello Tunasi"
        )
        # Nom de famille seul (Castanou) ne doit PAS matcher Yvan ou Modestine pour éviter faux positifs
        self.assertIsNone(
            match_author_in_database("Un livre écrit par Castanou seul", "Castanou", db_authors)
        )

    def test_publisher_db_matching_and_typos(self):
        db_pubs = ["Metanoia & Vie", "Société Biblique de Genève", "Excelsis", "Éditions LLB", "Editheos"]
        # Correspondance variante '&' / 'et'
        pub, score, _ = match_publisher_in_database("Publié par les Éditions Metanoia et Vie", "Metanoia et Vie", db_pubs)
        self.assertEqual(pub, "Metanoia & Vie")
        self.assertGreaterEqual(score, 0.9)

        # Tolérance typo (ExceIsis -> Excelsis)
        pub, score, _ = match_publisher_in_database("ExceIsis Éditions", "ExceIsis", db_pubs)
        self.assertEqual(pub, "Excelsis")
        self.assertGreaterEqual(score, 0.85)


    def test_scan_book_page_direct(self):
        # Image synthétique simulant une page de garde d'un livre du catalogue
        # Le code-barres n'est pas extrait de la photo : il est scanné au dos
        img = np.full((350, 500, 3), 245, dtype=np.uint8)
        cv2.putText(img, "LA GUERRE SPIRITUELLE", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (10, 10, 10), 2)
        cv2.putText(img, "Yvan Castanou", (40, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (30, 30, 30), 2)

        _, buf = cv2.imencode('.jpg', img)
        file_bytes = buf.tobytes()

        res = scan_book_page(file_bytes)
        self.assertTrue(res.get("ok"))
        candidates = res.get("candidates", {})
        # Pas de code-barres sur la page de garde (scanné au dos)
        self.assertEqual(candidates.get("isbn"), "")
        # Titre reconnu dans la base
        self.assertEqual(candidates.get("title", ""), "La Guerre Spirituelle")
        # Auteur avec nom et prénom capitalisés
        self.assertEqual(candidates.get("author", ""), "Yvan Castanou")
        # Métadonnées d'appartenance à la base de données
        fields_in_db = res.get("fields_in_db", {})
        self.assertTrue(fields_in_db.get("book_exists"))
        self.assertTrue(fields_in_db.get("author"))

    def test_ocr_scan_endpoint_json(self):
        img = np.full((350, 500, 3), 245, dtype=np.uint8)
        cv2.putText(img, "LA GUERRE SPIRITUELLE", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (10, 10, 10), 2)
        cv2.putText(img, "Yvan Castanou", (40, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (30, 30, 30), 2)
        _, buf = cv2.imencode('.jpg', img)
        b64 = base64.b64encode(buf.tobytes()).decode('ascii')

        body_payload = json.dumps({"image_base64": b64}).encode('utf-8')

        scope = {
            'type': 'http',
            'method': 'POST',
            'path': '/api/ocr/scan',
            'headers': [(b'content-type', b'application/json')],
        }
        async def receive():
            return {'type': 'http.request', 'body': body_payload}

        req = Request(scope, receive)
        res = asyncio.run(ocr_scan(req))
        self.assertTrue(res.get("ok"))
        # Pas d'ISBN extrait de la photo
        self.assertEqual(res.get("candidates", {}).get("isbn"), "")
        self.assertEqual(res.get("candidates", {}).get("title"), "La Guerre Spirituelle")
        self.assertTrue(res.get("fields_in_db", {}).get("book_exists"))



if __name__ == '__main__':
    unittest.main()

