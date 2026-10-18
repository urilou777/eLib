"""
app/ocr.py
-------------------------------------------------------------------------------
Service d'OCR haute fidélité pour l'extraction de texte sur les livres physiques
(pages de garde, couvertures 2D texturées, éclairage variable, angles).

Moteur : RapidOCR (ONNX Runtime / PaddleOCR DBNet++ & SVTR)
- 100% open-source (Apache 2.0), gratuit, local, sans API externe.
- Détection de texte arbitraire (polygones, rotations, textures papier).
- Heuristiques intelligentes dédiées aux ouvrages (ISBN, Titre, Auteur, Prix, Éditeur).
-------------------------------------------------------------------------------
"""

import io
import re
import unicodedata
from difflib import SequenceMatcher
import numpy as np
from PIL import Image, ImageOps

_ocr_engine = None


def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
        except Exception as e:
            print(f"[OCR] Erreur d'initialisation de RapidOCR: {e}")
            return None
    return _ocr_engine


def extract_isbn(text: str) -> str | None:
    """Extrait un ISBN-13 ou EAN-13 valide d'une chaîne de caractères."""
    if not text:
        return None
    # Recherche ISBN précédé de mot clé ou chaîne de 13 chiffres 978/979
    raw_candidates = re.findall(
        r'(?:ISBN(?:-1[03])?[\s:]*)?((?:97[89][\s-]*)?(?:(?:\d[\s-]*){9}[\dX]|\d{13}))',
        text,
        re.IGNORECASE
    )
    for c in raw_candidates:
        clean = re.sub(r'[\s\-]', '', c).upper()
        if (len(clean) == 13 and clean.isdigit() and clean.startswith(('978', '979'))) or (len(clean) == 10):
            return clean
    # Recherche directe d'un bloc de 13 chiffres 978... ou 979...
    m = re.search(r'(97[89]\d{10})', re.sub(r'[\s\-]', '', text))
    if m:
        return m.group(1)
    return None


def extract_price(text: str) -> float | None:
    """Extrait un prix en euros éventuel (ex: 12,00 € ou 15€)."""
    if not text:
        return None
    m = re.search(r'(\d{1,3}(?:[.,]\d{2})?)\s*(?:€|EUR)', text, re.IGNORECASE)
    if m:
        val_str = m.group(1).replace(',', '.')
        try:
            val = float(val_str)
            if 0 < val < 500:
                return val
        except ValueError:
            pass
    return None


def is_metadata_line(text: str) -> bool:
    """Identifie les mentions techniques à exclure du titre principal."""
    t = text.lower()
    meta_terms = [
        'isbn', 'dépôt légal', 'depot legal', 'imprimé en', 'imprime en',
        'droits réservés', 'tous droits', 'copyright', 'all rights',
        'tirage', 'achevé d\'imprimer', 'collection', 'prix :'
    ]
    return any(term in t for term in meta_terms)


def normalize_text(text: str) -> str:
    """Supprime les accents et caractères spéciaux pour la comparaison floue."""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text)
    no_accent = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', no_accent).lower()
    return re.sub(r'\s+', ' ', clean).strip()


def tokenize(text: str) -> set:
    """Extrait les mots-clés significatifs (> 1 caractère, hors mots vides)."""
    stopwords = {'de', 'du', 'des', 'le', 'la', 'les', 'un', 'une', 'et', 'en', 'au', 'aux', 'par', 'pour', 'sur', 'dans', 'a', 'd', 'l'}
    tokens = [w for w in normalize_text(text).split() if len(w) > 1 and w not in stopwords]
    return set(tokens)


def assemble_multiline_title(eligible_lines: list, page_h: float) -> str:
    """
    Assemble intelligemment un titre s'étendant sur plusieurs lignes
    en regroupant les lignes de forte proéminence typographique et de proximité verticale.
    """
    if not eligible_lines:
        return ""
    max_h = max(line["height"] for line in eligible_lines)
    # Lignes du titre : hauteur >= 40% de la hauteur max dans la zone haute/médiane
    title_candidates = [
        line for line in eligible_lines
        if line["height"] >= max_h * 0.35
    ]
    if not title_candidates:
        title_candidates = eligible_lines

    # Trier par position verticale (ordre naturel de lecture de haut en bas)
    title_candidates.sort(key=lambda x: x["center_y"])

    # Grouper les lignes consécutives formant le bloc de titre
    blocks = []
    current_block = [title_candidates[0]]

    for next_line in title_candidates[1:]:
        prev_line = current_block[-1]
        vertical_dist = next_line["center_y"] - prev_line["center_y"]
        max_line_h = max(prev_line["height"], next_line["height"])
        # Espace interligne toléré (jusqu'à 3.8 fois la hauteur de police pour les titres étalés)
        if 0 < vertical_dist <= max_line_h * 3.8:
            current_block.append(next_line)
        else:
            blocks.append(current_block)
            current_block = [next_line]
    blocks.append(current_block)

    # Prendre le bloc contenant la ligne maximale (cœur du titre)
    target_block = None
    for b in blocks:
        if any(l["height"] >= max_h * 0.90 for l in b):
            target_block = b
            break
    if not target_block:
        target_block = max(blocks, key=lambda b: sum(l["height"] for l in b))

    # Assemblage avec gestion des césures
    assembled_parts = []
    for line in target_block:
        txt = line["text"].strip()
        if assembled_parts and assembled_parts[-1].endswith("-"):
            assembled_parts[-1] = assembled_parts[-1][:-1] + txt
        else:
            assembled_parts.append(txt)

    return " ".join(assembled_parts).strip()


def format_sentence_case(text: str) -> str:
    """
    Capitalisation de phrase uniquement :
    Première lettre du titre en majuscule, tout le reste en minuscules.
    Majuscule rétablie uniquement après ponctuation forte (. : ? !).
    """
    if not text:
        return ""
    text = text.strip()
    if not text:
        return ""

    lowered = text.lower()
    chars = list(lowered)
    for i, c in enumerate(chars):
        if c.isalpha():
            chars[i] = c.upper()
            break
    res = "".join(chars)
    def cap_after_punct(m):
        return m.group(1) + m.group(2).upper()
    return re.sub(r'([:\.?!]\s+)([a-zàéèêîôû])', cap_after_punct, res)


def format_author_name(name: str) -> str:
    """
    Capitalisation sur le nom et prénom (chaque composante du nom en majuscule initiale).
    Ex: 'yvan castanou' -> 'Yvan Castanou', 'modestine castanou' -> 'Modestine Castanou'.
    """
    if not name:
        return ""
    parts = name.strip().split()
    formatted = []
    for p in parts:
        if '-' in p and not p.startswith('-') and not p.endswith('-'):
            formatted.append('-'.join(sub.capitalize() for sub in p.split('-')))
        elif "'" in p and not p.startswith("'") and not p.endswith("'"):
            pre, rest = p.split("'", 1)
            formatted.append(pre.capitalize() + "'" + rest.capitalize())
        else:
            formatted.append(p.capitalize())
    return " ".join(formatted)


def match_author_in_database(raw_text: str, candidate_line: str, db_authors: list) -> str | None:
    """
    Recherche un auteur de la base dans le texte avec correspondance stricte sur NOM ET PRÉNOM,
    avec tolérance aux fautes d'orthographe et coquilles OCR (ex: Modestlne -> Modestine, Marcello Tunassi -> Marcello Tunasi).
    Exclut tout faux positif basé sur le seul nom de famille (ex: Castanou seul sans Yvan ou sans Modestine).
    """
    raw_norm = normalize_text(raw_text)
    raw_tokens = raw_norm.split()
    raw_compact = raw_norm.replace(' ', '')
    cand_norm = normalize_text(candidate_line)

    best_author = None
    best_score = 0.0

    for auth in db_authors:
        auth_clean = auth.strip()
        auth_norm = normalize_text(auth_clean)
        auth_tokens = [tok for tok in auth_norm.split() if len(tok) > 1]

        # Un auteur avec prénom et nom (ex: Modestine Castanou, Yvan Castanou)
        if len(auth_tokens) >= 2:
            # Vérifier chaque composante (prénom ET nom) soit exacte, soit avec faute d'orthographe mineure
            matched_tokens = []
            for atok in auth_tokens:
                if atok in raw_tokens or atok in raw_compact:
                    matched_tokens.append(atok)
                else:
                    # Tolérance coquille OCR (ex: 'modestlne' pour 'modestine', ratio >= 0.82)
                    for rt in raw_tokens:
                        if len(rt) > 3 and SequenceMatcher(None, atok, rt).ratio() >= 0.82:
                            matched_tokens.append(atok)
                            break

            # Strict : toutes les composantes de prénom ET nom doivent être validées
            if len(matched_tokens) == len(auth_tokens):
                seq = SequenceMatcher(None, auth_norm, cand_norm).ratio()
                score = 1.0 if seq > 0.5 else 0.95
                if score > best_score:
                    best_score = score
                    best_author = auth_clean
        elif len(auth_tokens) == 1:
            if auth_tokens[0] in raw_tokens and len(auth_tokens[0]) > 3:
                seq = SequenceMatcher(None, auth_norm, cand_norm).ratio()
                if seq > 0.85 and seq > best_score:
                    best_score = seq
                    best_author = auth_clean

    return best_author


def match_publisher_in_database(raw_text: str, candidate_line: str, db_publishers: list) -> tuple[str | None, float, str | None]:
    """
    Recherche un éditeur de la base de données avec correspondance intelligente et tolérance
    aux variantes (ex: 'Éditions Metanoia & Vie' vs 'Metanoia et Vie', 'Excelsis' vs 'Editions Excelsis',
    fautes de frappe OCR comme 'Editions BLE' pour 'BLF Éditions').
    Retourne un tuple : (editeur_canonique, score_confiance, texte_brut_detecte).
    """
    if not db_publishers:
        return None, 0.0, None

    raw_norm = normalize_text(raw_text).replace('&', ' et ')
    raw_tokens = set(raw_norm.split())
    cand_norm = normalize_text(candidate_line).replace('&', ' et ')

    best_pub = None
    best_score = 0.0
    matched_snippet = None

    stop_pub_words = {'editions', 'edition', 'les', 'de', 'la', 'le', 'et', 'collection', 'publishing', 'media', 'maison'}

    for pub in db_publishers:
        pub_clean = pub.strip()
        pub_norm = normalize_text(pub_clean).replace('&', ' et ')
        pub_tokens = [tok for tok in pub_norm.split() if tok not in stop_pub_words and len(tok) > 1]

        # 1. Correspondance de séquence directe (très forte si >= 0.78)
        seq = SequenceMatcher(None, pub_norm, cand_norm).ratio()
        if seq >= 0.78 and seq > best_score:
            best_score = seq
            best_pub = pub_clean
            matched_snippet = candidate_line

        # 2. Correspondance des termes clés de la marque (ex: 'metanoia', 'excelsis', 'editheos', 'esdras')
        if pub_tokens:
            matches = [
                tok for tok in pub_tokens
                if tok in raw_tokens or any(SequenceMatcher(None, tok, rt).ratio() >= 0.82 for rt in raw_tokens)
            ]
            if len(matches) == len(pub_tokens):
                score = 0.95
                if score > best_score:
                    best_score = score
                    best_pub = pub_clean
                    matched_snippet = candidate_line

    return best_pub, best_score, matched_snippet



def get_recorded_catalog_data() -> dict:
    """Charge l'ensemble des données enregistrées du catalogue pour comparaison et enrichissement."""
    try:
        from . import db
        with db.tx() as c:
            books = [dict(r) for r in c.execute("""
                SELECT b.id, b.code, b.title, b.volume, b.series, b.author, b.publisher, b.price,
                       COALESCE((SELECT SUM(l.qty_in - COALESCE((SELECT SUM(a.qty) FROM allocations a WHERE a.lot_id=l.id), 0)) FROM lots l WHERE l.book_id=b.id), 0) AS stock
                FROM books b
                WHERE b.active = 1
            """).fetchall()]
            authors = [r[0] for r in c.execute("SELECT DISTINCT author FROM books WHERE author IS NOT NULL AND TRIM(author) != ''").fetchall()]
            publishers_db = [r[0] for r in c.execute("SELECT DISTINCT publisher FROM books WHERE publisher IS NOT NULL AND TRIM(publisher) != ''").fetchall()]
            publishers_opt = [r[0] for r in c.execute("SELECT label FROM dropdown_options WHERE group_key = 'publisher'").fetchall()]
            publishers = list(set(publishers_db + publishers_opt))
            return {"books": books, "authors": authors, "publishers": publishers}
    except Exception:
        return {"books": [], "authors": [], "publishers": []}


def find_matching_catalog_book(raw_text: str, candidate_title: str, candidate_isbn: str, candidate_author: str, catalog_books: list = None) -> tuple[dict | None, list]:
    """Compare le texte reconnu avec les livres déjà enregistrés dans le catalogue.
    Retourne un tuple : (meilleure_correspondance, liste_des_candidats_pertinents)."""
    if catalog_books is None:
        ref_data = get_recorded_catalog_data()
        catalog_books = ref_data.get("books", [])

    if not catalog_books:
        return None, []

    # 1. Correspondance exacte par code ISBN / EAN
    if candidate_isbn:
        clean_isbn = re.sub(r'[\s\-]', '', candidate_isbn)
        for b in catalog_books:
            b_code = re.sub(r'[\s\-]', '', str(b.get("code") or ""))
            if b_code and b_code == clean_isbn:
                match = {**b, "match_type": "exact_isbn", "confidence": 1.0, "match_reason": "Code ISBN identique"}
                return match, [match]

    # 2. Correspondance floue par titre et auteur (avec résilience aux espaces omis)
    raw_norm = normalize_text(raw_text)
    raw_compact = re.sub(r'\s+', '', raw_norm)
    title_norm = normalize_text(candidate_title)
    title_compact = re.sub(r'\s+', '', title_norm)

    all_matches = []

    for b in catalog_books:
        b_title = b.get("title") or ""
        b_author = b.get("author") or ""
        b_title_tokens = tokenize(b_title)
        if not b_title_tokens:
            continue

        # Vérifier quels tokens du livre apparaissent dans le texte OCR
        tokens_found = [tok for tok in b_title_tokens if tok in raw_norm or tok in raw_compact]
        token_coverage = len(tokens_found) / len(b_title_tokens)

        # Si le titre complet (compacté) est présent dans le texte OCR
        b_title_norm = normalize_text(b_title)
        b_title_compact = re.sub(r'\s+', '', b_title_norm)
        exact_sub = 1.0 if (b_title_compact and b_title_compact in raw_compact) else 0.0

        # Similarité de séquence
        seq_sim = SequenceMatcher(None, b_title_norm, title_norm).ratio()

        score = max(token_coverage * 0.92, exact_sub, seq_sim * 0.88)

        # Bonus si l'auteur du livre apparaît aussi dans le texte OCR
        auth_matched = False
        if b_author:
            b_auth_tokens = tokenize(b_author)
            if b_auth_tokens:
                auth_found = [tok for tok in b_auth_tokens if tok in raw_norm or tok in raw_compact]
                if len(auth_found) == len(b_auth_tokens):
                    score = min(score + 0.15, 1.0)
                    auth_matched = True
                elif auth_found:
                    score = min(score + 0.08, 1.0)
                    auth_matched = True

        if score >= 0.38:
            reason = "Titre identique" if score > 0.90 else ("Titre similaire + Auteur" if auth_matched else "Titre similaire")
            all_matches.append({
                **b,
                "match_type": "fuzzy_title",
                "confidence": round(min(score, 1.0), 2),
                "match_reason": reason
            })

    all_matches.sort(key=lambda m: m["confidence"], reverse=True)
    best_match = all_matches[0] if (all_matches and all_matches[0]["confidence"] >= 0.65) else None

    return best_match, all_matches[:5]


def scan_book_page(image_bytes: bytes, catalog_books: list = None) -> dict:
    """
    Scanne une image de page de garde ou de couverture de livre et extrait
    les textes avec heuristiques de qualification (Titre, Auteur, ISBN, Prix).
    """
    engine = get_ocr_engine()
    if not engine:
        return {
            "ok": False,
            "error": "Moteur OCR non initialisé. Veuillez installer rapidocr_onnxruntime."
        }

    try:
        # 1. Chargement et normalisation de l'image
        pil_img = Image.open(io.BytesIO(image_bytes))

        # Redressement automatique selon les métadonnées EXIF du smartphone
        try:
            pil_img = ImageOps.exif_transpose(pil_img)
        except Exception:
            pass

        # Conversion en RGB
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")

        # Redimensionnement conservant le ratio pour rapidité et netteté (max 1600px)
        w, h = pil_img.size
        max_dim = 1600
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            new_w, new_h = int(w * scale), int(h * scale)
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            w, h = new_w, new_h

        img_np = np.array(pil_img)

        # 2. Exécution OCR (Detection DBNet + Recognition SVTR)
        result, elapse = engine(img_np)
        if not result:
            return {
                "ok": True,
                "candidates": {
                    "title": "",
                    "author": "",
                    "isbn": "",
                    "price": None,
                    "publisher": ""
                },
                "lines": [],
                "raw_text": "",
                "message": "Aucun texte détecté sur l'image."
            }

        # 3. Extraction et enrichissement des lignes
        parsed_lines = []
        full_text_list = []
        found_isbn = None
        found_price = None

        for item in result:
            box, text, conf = item[0], str(item[1]).strip(), float(item[2])
            if not text or conf < 0.35:
                continue

            full_text_list.append(text)

            # Recherche d'un prix
            if found_price is None:
                cand_price = extract_price(text)
                if cand_price is not None:
                    found_price = cand_price

            # Calcul dimensions boîte
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            box_w = max(xs) - min(xs)
            box_h = max(ys) - min(ys)
            center_y = sum(ys) / len(ys)
            center_x = sum(xs) / len(xs)

            parsed_lines.append({
                "text": text,
                "conf": round(conf, 2),
                "box": box,
                "width": round(box_w, 1),
                "height": round(box_h, 1),
                "center_y": round(center_y, 1),
                "center_x": round(center_x, 1)
            })

        # 4. Comparaison avec les données enregistrées (Auteurs, Éditeurs) & Heuristiques
        ref_data = get_recorded_catalog_data()
        catalog_books = catalog_books or ref_data.get("books", [])
        recorded_authors = ref_data.get("authors", [])
        recorded_publishers = ref_data.get("publishers", [])

        candidate_title = ""
        candidate_author = ""
        candidate_publisher = ""
        matched_db_author = None
        matched_db_publisher = None
        author_ocr_snippet = None
        publisher_ocr_snippet = None
        corrections = {}

        raw_text = "\n".join(full_text_list)

        # 4.1 Recherche stricte d'un auteur et d'un éditeur dans la base de données
        for pl in parsed_lines:
            txt = pl["text"]

            if not candidate_author:
                m_auth = match_author_in_database(raw_text, txt, recorded_authors)
                if m_auth:
                    candidate_author = m_auth
                    matched_db_author = m_auth
                    author_ocr_snippet = txt
                    pl["tag"] = "author"

            if not candidate_publisher:
                m_pub, m_pub_score, m_snippet = match_publisher_in_database(raw_text, txt, recorded_publishers)
                if m_pub:
                    candidate_publisher = m_pub
                    matched_db_publisher = m_pub
                    publisher_ocr_snippet = m_snippet or txt
                    pl["tag"] = "publisher"

        # 4.2 Recherche heuristique classique si non trouvés dans la base
        for pl in parsed_lines:
            txt = pl["text"]
            txt_low = txt.lower()

            # Auteur explicite (ex: "Pasteur Yvan Castanou", "Par Marcello Tunasi")
            m_auth = re.match(r'^(?:écrit par|par|de|auteur\s*:?)\s*[:\-]?\s*(.*)', txt, flags=re.IGNORECASE)
            if m_auth and not candidate_author:
                cand = m_auth.group(1).strip()
                if len(cand) > 2:
                    candidate_author = format_author_name(cand)
                    pl["tag"] = "author"
                    continue

            # Titres ecclésiastiques / honorifiques (Pasteur, Dr, etc.)
            m_title_auth = re.match(r'^(?:pasteur|docteur|dr\.?|évangéliste|apôtre|pr\.?)\s*(.*)', txt, flags=re.IGNORECASE)
            if m_title_auth and not candidate_author:
                candidate_author = format_author_name(txt.strip())
                pl["tag"] = "author"
                continue

            # Éditeur heuristique
            pub_triggers = ['éditions', 'editions', 'publishing', 'cité royale', 'blf', 'première partie']
            if any(pt in txt_low for pt in pub_triggers) and not candidate_publisher:
                candidate_publisher = format_author_name(txt)
                pl["tag"] = "publisher"

        # 4.3 Déterminer le titre principal (gestion robuste des titres sur plusieurs lignes)
        eligible_title_lines = [
            pl for pl in parsed_lines
            if not is_metadata_line(pl["text"])
            and pl.get("tag") not in ("author", "publisher")
            and pl["text"] != candidate_author
            and pl["text"] != candidate_publisher
            and pl["center_y"] < h * 0.85
            and len(pl["text"]) > 1
        ]

        if eligible_title_lines:
            raw_assembled_title = assemble_multiline_title(eligible_title_lines, h)
            max_line_h = max(l["height"] for l in eligible_title_lines)
            top_line = next((l for l in eligible_title_lines if l["height"] >= max_line_h * 0.95), eligible_title_lines[0])
            # Capitalisation de phrase UNIQUEMENT pour le titre (1ère lettre majuscule, reste minuscules)
            candidate_title = format_sentence_case(raw_assembled_title)
        else:
            top_line = None

        # Si l'auteur n'a toujours pas été trouvé, chercher un nom isolé hors titre
        if not candidate_author and top_line and len(eligible_title_lines) > 1:
            for pl in eligible_title_lines:
                if pl["text"] not in candidate_title and pl["height"] < top_line["height"] * 0.65:
                    words = pl["text"].split()
                    if 1 <= len(words) <= 4 and not any(char.isdigit() for char in pl["text"]):
                        candidate_author = format_author_name(pl["text"])
                        break

        if candidate_author and candidate_author not in recorded_authors:
            candidate_author = format_author_name(candidate_author)
        if candidate_publisher and candidate_publisher not in recorded_publishers:
            candidate_publisher = format_author_name(candidate_publisher)

        # Détection des corrections / coquilles orthographiques
        if matched_db_author and author_ocr_snippet:
            clean_snip = normalize_text(author_ocr_snippet)
            clean_auth = normalize_text(matched_db_author)
            if clean_snip != clean_auth:
                corrections["author"] = {
                    "original": author_ocr_snippet,
                    "corrected": matched_db_author,
                    "reason": "Orthographe BDD appliquée"
                }

        if matched_db_publisher and publisher_ocr_snippet:
            clean_snip = normalize_text(publisher_ocr_snippet)
            clean_pub = normalize_text(matched_db_publisher)
            if clean_snip != clean_pub:
                corrections["publisher"] = {
                    "original": publisher_ocr_snippet,
                    "corrected": matched_db_publisher,
                    "reason": "Éditeur BDD officiel appliqué"
                }

        # 5. Comparaison intelligente avec les livres déjà enregistrés dans le catalogue (sans barcode de photo)
        matched_book, matches_list = find_matching_catalog_book(
            raw_text=raw_text,
            candidate_title=candidate_title,
            candidate_isbn="",
            candidate_author=candidate_author,
            catalog_books=catalog_books
        )

        if matched_book and matched_book.get("confidence", 0) >= 0.85:
            if matched_book.get("title"):
                candidate_title = matched_book["title"]
            if matched_book.get("author") and not candidate_author:
                candidate_author = matched_book["author"]
            if matched_book.get("price") and found_price is None:
                found_price = matched_book["price"]
            if matched_book.get("publisher") and not candidate_publisher:
                candidate_publisher = matched_book["publisher"]

        fields_in_db = {
            "author": bool(candidate_author and (matched_db_author or candidate_author in recorded_authors)),
            "publisher": bool(candidate_publisher and (matched_db_publisher or candidate_publisher in recorded_publishers)),
            "title": bool(matched_book and matched_book.get("confidence", 0) >= 0.85),
            "book_exists": bool(matched_book and matched_book.get("confidence", 0) >= 0.85)
        }

        return {
            "ok": True,
            "candidates": {
                "title": candidate_title,
                "author": candidate_author,
                "isbn": "",  # Le code-barres n'est pas extrait de la photo de face : il est scanné au dos
                "price": found_price,
                "publisher": candidate_publisher
            },
            "fields_in_db": fields_in_db,
            "corrections": corrections,
            "matched_book": matched_book,
            "matches": matches_list,
            "lines": parsed_lines,
            "raw_text": raw_text,
            "stats": {
                "line_count": len(parsed_lines),
                "image_size": f"{w}x{h}"
            }
        }


    except Exception as e:
        return {
            "ok": False,
            "error": f"Erreur lors de l'analyse OCR : {str(e)}"
        }
