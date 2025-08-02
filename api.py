from flask import Blueprint, request, jsonify, redirect
from bson.objectid import ObjectId
import requests
import os
from app import reisen

api_key = os.getenv("API_KEY")

api_bp = Blueprint("api", __name__, url_prefix="/api")

@api_bp.route('/google_places')
def google_places():
    query = request.args.get('query')
    url = 'https://maps.googleapis.com/maps/api/place/textsearch/json'
    params = {'query': query, 'key': GOOGLE_API_KEY}
    r = requests.get(url, params=params)
    
    return jsonify(r.json())

@api_bp.route('/place_photo')
def place_photo():
    ref = request.args.get("photo_reference")
    
    r = requests.get("https://maps.googleapis.com/maps/api/place/photo", params={
        "photo_reference": ref,
        "maxwidth": 400,
        'key': GOOGLE_API_KEY
    }, allow_redirects=False)
    return redirect(r.headers["Location"])

# === Flugangebote abfragen ===
@api_bp.route("/suche_fluege", methods=["POST"])
def suche_fluege():
    daten = request.get_json()
    start = daten["start"]
    ziel = daten["ziel"]
    startdatum = daten["startdatum"]

    token = hole_token()
    url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "originLocationCode": start,
        "destinationLocationCode": ziel,
        "departureDate": startdatum,
        "adults": 1,
        "max": 5,
        "nonStop": "false"
    }

    res = requests.get(url, headers=headers, params=params)
    try:
        res.raise_for_status()
        return jsonify(res.json())
    except requests.HTTPError as e:
        return jsonify({"error": str(e), "details": res.text}), 500
    
@api_bp.route("/get_iata_code")
def get_iata_code():
    ort = request.args.get("ort")
    if not ort:
        return jsonify({"error": "Missing 'ort'"}), 400

    token = hole_token()  
    res = requests.get(
        "https://test.api.amadeus.com/v1/reference-data/locations",
        headers={"Authorization": f"Bearer {token}"},
        params={"keyword": ort, "subType": "AIRPORT,CITY", "page[limit]": 10}
    )
    data = res.json()
    treffer = data.get("data", [])

    if not treffer:
        return jsonify({"error": "No match"}), 404

    ort_lower = ort.lower()

    # 1. Genau passende Stadt oder Flughafenname
    for eintrag in treffer:
        if (eintrag.get("address", {}).get("cityName", "").lower() == ort_lower or
            eintrag.get("name", "").lower() == ort_lower):
            return jsonify({"code": eintrag["iataCode"]})

    # 2. Teilweise Übereinstimmung
    for eintrag in treffer:
        if ort_lower in eintrag.get("address", {}).get("cityName", "").lower():
            return jsonify({"code": eintrag["iataCode"]})

    # 3. Fallback – nimm den ersten
    return jsonify({"code": treffer[0]["iataCode"]})
    
@api_bp.route("/flug_hinzufuegen", methods=["POST"])
def flug_hinzufuegen():
    daten = request.get_json()
    reise_id = daten.get("reise_id")
    flug = daten.get("flug")

    if not reise_id or not flug:
        return jsonify({"error": "Fehlende Daten"}), 400

    reisen.update_one(
        {"_id": ObjectId(reise_id)},
        {"$push": {"fluege": flug}}
    )

    return jsonify({"status": "Flug hinzugefügt"})


def hole_token():
    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": API_KEY,
        "client_secret": API_SECRET
    }
    res = requests.post(url, headers=headers, data=data)
    res.raise_for_status()
    return res.json()["access_token"]

def get_iata(ort, token):
    res = requests.get(
        "https://test.api.amadeus.com/v1/reference-data/locations",
        headers={"Authorization": f"Bearer {token}"},
        params={"keyword": ort, "subType": "AIRPORT,CITY", "page[limit]": 1}
    )
    res.raise_for_status()
    daten = res.json().get("data", [])
    return daten[0]["iataCode"] if daten else None





