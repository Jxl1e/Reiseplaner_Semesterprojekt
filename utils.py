import re
from difflib import get_close_matches
import requests
from rapidfuzz import process
import os


def validiere_und_normalisiere_stopp(stopp, country_code):
    import re
    match = re.match(r"(\d{4,5})\s+(.+)", stopp)
    if match:
        plz = match.group(1)
        ort = match.group(2)
    else:
        plz = None
        ort = stopp

    stopp_korrigiert = fuzzy_korrektur(ort)

    suchstring = f"{plz} {stopp_korrigiert}" if plz else stopp_korrigiert

    valider_stopp = finde_ort_ueber_geonames(suchstring, country_code)
    return valider_stopp or suchstring

def lade_staedte(pfad="geonames/cities1000.txt"):
    staedte = set()
    if not os.path.exists(pfad):
        print(f"Warnung: Datei {pfad} nicht gefunden!")
        return []

    with open(pfad, encoding="utf-8") as f:
        for zeile in f:
            teile = zeile.strip().split('\t')
            if len(teile) >= 4:
                name = teile[1]
                alternativen = teile[3].split(',') if teile[3] else []
                staedte.add(name)
                staedte.update(alternativen)
    return list(staedte)

# Einmalig beim Start laden
alle_bekannten_orte = lade_staedte("geonames/cities1000.txt")

def fuzzy_korrektur(ort, orts_liste=alle_bekannten_orte):
    ergebnis = process.extractOne(ort, orts_liste, score_cutoff=80)
    if ergebnis:
        return ergebnis[0]  # Korrigierter Name
    return ort  # Original beibehalten, wenn nichts passt

def finde_ort_ueber_nominatim(ort, country_code=None):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': ort,
        'format': 'json',
        'limit': 5
    }

    if country_code:
        params['countrycodes'] = country_code.lower()

    headers = {
        'User-Agent': 'ReiseplanerApp/1.0 (julz.woehrle@gmx.de)'
    }
    response = requests.get(url, params=params, headers=headers)
    ergebnisse = response.json()
    if not ergebnisse:
        return None
    
    for res in ergebnisse:
        if res.get('class') == 'place' and res.get('type') in ['city', 'town', 'village']:
            return res['display_name']
        
    return ergebnisse[0]['display_name']

def finde_ort_ueber_geonames(plz_ort, country_code):
    print(f"Suche nach Ort: '{plz_ort}'")
    import re

    # Prüfe, ob die Eingabe eine PLZ und Ort hat
    match = re.match(r"(\d{4,5})\s+(.+)", plz_ort)
    if match:
        plz = match.group(1)
        ort = match.group(2)
        params = {
            "maxRows": 1,
            "country": country_code,
            "username": "jxl1e"
        }
        # Suche nach PLZ und Ort
        params["postalcode"] = plz
        params["placename"] = ort
    else:
        # Nur Ort, keine PLZ
        ort = plz_ort
        params = {
            "maxRows": 1,
            "country": country_code,
            "username": "jxl1e",
            "placename": ort
        }

    url = "http://api.geonames.org/postalCodeSearchJSON"

    try:
        r = requests.get(url, params=params, timeout=5)
        data = r.json()
        print(f"GeoNames Antwort für {plz_ort}: {data}")
    except Exception as e:
        print("GeoNames Fehler:", e)
        return None

    if data.get("postalCodes"):
        result = data["postalCodes"][0]
        return f"{result.get('postalCode')} {result.get('placeName')}"
    else:
        print(f"Keine Ergebnisse für {plz_ort} in GeoNames")
        return None
