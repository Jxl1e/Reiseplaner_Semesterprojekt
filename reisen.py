from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from bson.objectid import ObjectId
import re
import requests
import json
from app import db, reisen
from utils import fuzzy_korrektur, finde_ort_ueber_geonames, finde_ort_ueber_nominatim, validiere_und_normalisiere_stopp
from api import hole_token, get_iata

reisen_bp = Blueprint("reisen", __name__, url_prefix="")

reisen = db["reisen"]

@reisen_bp.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    return redirect(url_for('reisen.dashboard'))

@reisen_bp.route("/dashboard")
@login_required
def dashboard():
    user_reisen = [
        {**reise, "_id": str(reise["_id"])}
        for reise in reisen.find({"user_id": current_user.id})
    ]
    return render_template('dashboard.html', reisen=user_reisen)

@reisen_bp.route("/initial_dashboard")
@login_required
def initial_dashboard():
    return render_template('initial_dashboard.html')

@reisen_bp.route("/impressum")
def impressum():
    return render_template("impressum.html")

@reisen_bp.route("/add")
@login_required
def add():
    zielland = request.args.get("zielland", None)
    zielland_name = request.args.get("zielland_name", None)
    if not zielland:
        flash("Bitte wählen Sie ein Zielland aus.", "warning")
        return redirect(url_for("reisen.index"))
    return render_template("reiseverwaltung.html", zielland=zielland, zielland_name=zielland_name)

@reisen_bp.route("/ergebnisse", methods=["GET", "POST"])
@login_required
def ergebnisse():
    if request.method == "POST":
        reiseart = request.form.get('reiseart', '').strip().lower()
        zielland = request.form.get('zielland')
        zielland_name = request.form.get('zielland_name')
        anreise = request.form.get('anreise')
        abreise = request.form.get('abreise')

        zielort = None
        zielort_plz = None
        korrigierter_zielort = None
        stopps = []

        # Nur bei Roadtrip oder Städetrip verarbeiten wir Zielort
        if reiseart in ["roadtrip", "städtetrip", "staedtetrip"]:
            zielort_roh = request.form.get('zielort', '').strip()
            if zielort_roh:
                match = re.match(r"(\d{5})\s+(.+)", zielort_roh)
                if match:
                    zielort_plz = match.group(1)
                    ort = match.group(2)
                else:
                    ort = zielort_roh

                zielort_korrigiert = fuzzy_korrektur(ort)
                korrigierter_zielort = finde_ort_ueber_geonames(zielort_korrigiert, country_code=zielland)
                if korrigierter_zielort is None:
                    korrigierter_zielort = finde_ort_ueber_nominatim(zielort_korrigiert, country_code=zielland) or zielort_korrigiert

        # Nur bei Roadtrip: Zwischenstopps verarbeiten
        if reiseart == "roadtrip":
            stopps_optionen = request.form.get('stopps_option')
            manuelle_stopps_raw = request.form.get('zwischenstopps', "")
            if stopps_optionen == "manuell" and manuelle_stopps_raw:
                manuelle_stopps = [s.strip() for s in manuelle_stopps_raw.split(",") if s.strip() and not s.strip().isdigit()]
                for stopp in manuelle_stopps:
                    match_stopp = re.match(r"(\d{4,5})\s+(.+)", stopp)
                    if match_stopp:
                        plz_stopp = match_stopp.group(1)
                        ort_stopp = match_stopp.group(2)
                    else:
                        plz_stopp = None
                        ort_stopp = stopp

                    ort_korrigiert = fuzzy_korrektur(ort_stopp)
                    suchstring = f"{plz_stopp} {ort_korrigiert}" if plz_stopp else ort_korrigiert

                    stopp_vollname = finde_ort_ueber_geonames(suchstring, country_code=zielland)
                    if stopp_vollname is None:
                        stopp_vollname = finde_ort_ueber_nominatim(suchstring, country_code=zielland) or suchstring

                    stopps.append(stopp_vollname)

        # Städetrip-spezifische Sehenswürdigkeiten
        sehenswuerdigkeiten_raw = request.form.get('sehenswuerdigkeiten') or '[]'
        try:
            sehenswuerdigkeiten_liste = json.loads(sehenswuerdigkeiten_raw)
            if not isinstance(sehenswuerdigkeiten_liste, list):
                sehenswuerdigkeiten_liste = []
        except (json.JSONDecodeError, TypeError):
            sehenswuerdigkeiten_liste = []

        sehenswuerdigkeiten_bereinigt = [s.strip() for s in sehenswuerdigkeiten_liste if s.strip()]

        # Badeurlaub-spezifische Felder (optional)
        hotelname = request.form.get('hotelname')
        flug_von = request.form.get('von')
        flug_nach = request.form.get('nach')
        fluege = []
        if reiseart == "badeurlaub" and flug_von and flug_nach and anreise:
            try:
                token = hole_token()  # Nur EIN Aufruf

                code_von = get_iata(flug_von, token)
                code_nach = get_iata(flug_nach, token)

                if code_von and code_nach:
                    headers = {"Authorization": f"Bearer {token}"}
                    params = {
                        "originLocationCode": code_von,
                        "destinationLocationCode": code_nach,
                        "departureDate": anreise,
                        "adults": 1,
                        "max": 5,
                        "nonStop": "false"
                    }
                    res = requests.get("https://test.api.amadeus.com/v2/shopping/flight-offers", headers=headers, params=params)
                    res.raise_for_status()
                    fluege = res.json().get("data", [])
            except Exception as e:
                print("Fehler bei Flugsuche:", e)
                fluege = []
        

        # Speichere alle Daten in Session
        session['reise_daten'] = {
            'reiseart': reiseart,
            'zielland': zielland,
            "zielland_name": zielland_name,
            'anreise': anreise,
            'abreise': abreise,
            'zielort': korrigierter_zielort,
            'zielort_plz': zielort_plz,
            'stopps': stopps,
            'sehenswuerdigkeiten': sehenswuerdigkeiten_bereinigt,
            'hotelname': hotelname,
            'flug_von': flug_von,
            'flug_nach': flug_nach,
            'fluege': fluege
        }
        print("Reisedaten in Session:", session)

        # Template je nach Reiseart auswählen
        template_name = {
            "badeurlaub": "ergebnisse_badeurlaub.html",
            "staedtetrip": "ergebnisse_staedtetrip.html",
            "städtetrip": "ergebnisse_staedtetrip.html",
            "roadtrip": "ergebnisse.html"
        }.get(reiseart, "ergebnisse.html")

        return render_template(template_name, reisedaten=session['reise_daten'])

    else:
        if 'reise_daten' in session:
            reisedaten = session['reise_daten']
            template_name = {
                "badeurlaub": "ergebnisse_badeurlaub.html",
                "staedtetrip": "ergebnisse_staedtetrip.html",
                "städtetrip": "ergebnisse_staedtetrip.html",
                "roadtrip": "ergebnisse.html"
            }.get(reisedaten.get('reiseart', ''), "ergebnisse.html")

            return render_template(template_name, reisedaten=reisedaten)
        else:
            # Hier z.B. zurück zum Startformular
            return redirect(url_for('reisen_bp.startseite'))



@reisen_bp.route("/reise_speichern", methods=["POST"])
@login_required
def reise_speichern():
    zielort = request.form.get('zielort')
    zielland = request.form.get('zielland')
    zielland_name = request.form.get('zielland_name')
    zielort_plz = request.form.get('zielort_plz')
    reiseart = request.form.get('reiseart') 
    anreise = request.form.get('anreise')
    abreise = request.form.get('abreise')

    reise = {
        "user_id": current_user.id,
        "zielort": zielort,
        "zielland": zielland,
        "zielland_name": zielland_name,
        "zielort_plz": zielort_plz,
        "reiseart": reiseart,
        "anreise": anreise,
        "abreise": abreise
    }


    if reiseart == "roadtrip":
        stopps = request.form.getlist('stopps')
        validierte_stopps = []
        for stopp in stopps:
            valider_stopp = validiere_und_normalisiere_stopp(stopp, zielland)
            validierte_stopps.append(valider_stopp)
        reise["stopps"] = validierte_stopps

    elif reiseart == "städtetrip":
        sehenswuerdigkeiten = request.form.getlist('sehenswuerdigkeiten')
        print("Sehenswürdigkeiten aus Formular:", sehenswuerdigkeiten)
        reise["sehenswuerdigkeiten"] = sehenswuerdigkeiten

    elif reiseart == "badeurlaub":
        hotel_json = request.form.get('hotel')
        if hotel_json:
            try:
                hotels = json.loads(hotel_json)
                reise["hotels"] = hotels
            except Exception as e:
                print("Hotel-JSON konnte nicht geladen werden:", e)
                reise["hotels"] = []
        fluege_json = request.form.get('fluege') 
        if fluege_json:
            try:
                fluege = json.loads(fluege_json)
                reise["fluege"] = fluege
            except Exception:
                reise["fluege"] = []

    else:
        return "Unbekannte Reiseart", 400

    print("Reise, die gespeichert wird:")
    print(reise)

    reisen.insert_one({k: v for k, v in reise.items() if v})

    return redirect(url_for('reisen.dashboard'))


@reisen_bp.route("/autocomplete_ort")
def autocomplete_ort():
    query = request.args.get("q", "")
    country = request.args.get("country", "")
    if not query or not country:
        return jsonify(results=[])

    geo_username = "jxl1e"
    url = "http://api.geonames.org/postalCodeSearchJSON"
    params = {
        "maxRows": 10,
        "username": geo_username,
        "country": country
    }

    import re
    match = re.match(r"(\d{4,5})\s+(.+)", query)
    if match:
        # Wenn "PLZ Ort" geliefert wird
        plz = match.group(1)
        ort = match.group(2)
        params["postalcode_startsWith"] = plz
        params["placename_startsWith"] = ort
    elif query.isdigit():
        params["postalcode_startsWith"] = query
    else:
        params["placename_startsWith"] = query

    try:
        r = requests.get(url, params=params, timeout=5)
        data = r.json()
    except Exception as e:
        print("GeoNames Fehler:", e)
        return jsonify(results=[])

    results = []
    for item in data.get("postalCodes", []):
        plz = item.get("postalCode", "")
        ort = item.get("placeName", "")
        results.append(f"{plz} {ort}")

    return jsonify(results=results)


def generiere_vorgeschlagene_stopps():
    return["Leipzig", "Dresden", "Erfurt"]

@reisen_bp.route("/anzeigen/<reise_id>", methods=["GET", "POST"])
@login_required
def anzeigen(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Ungültige Reise-ID", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
    
    stopps = reise.get("stopps")
    if not isinstance(stopps, list):
        stopps = [] 
    reise["stopps"] = stopps

    hotels = reise.get("hotels")
    if not isinstance(hotels, list):
        hotels = []
    reise["hotels"] = hotels


    return render_template('anzeigen.html', reise=reise, reise_id=oid)

@reisen_bp.route("anzeigen_staedtetrip/<reise_id>", methods=["GET", "POST"])
@login_required
def anzeigen_staedtetrip(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Ungültige Reise_ID", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
    
    sehenswuerdigkeiten = reise.get("sehenswuerdigkeiten")
    if not isinstance(sehenswuerdigkeiten, list):
        sehenswuerdigkeiten = []
    reise["sehenswuerdigkeiten"] = sehenswuerdigkeiten
    
    hotels = reise.get("hotels")
    if not isinstance(hotels, list):
        hotels = []
    reise["hotels"] = hotels

    return render_template("anzeigen_staedtetrip.html", reise=reise, reise_id=oid)

@reisen_bp.route("anzeigen_badeurlaub/<reise_id>", methods=["GET", "POST"])
@login_required
def anzeigen_badeurlaub(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Ungültige Reise_ID", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
    
    return render_template("anzeigen_badeurlaub.html", reise=reise, reise_id=oid)

@reisen_bp.route("/edit/<reise_id>", methods=["GET", "POST"])
@login_required
def edit(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Ungültige Reise-ID", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
   
    return render_template("bearbeiten.html", reise=reise)

@reisen_bp.route("/edit_staedtetrip/<reise_id>", methods=["GET", "POST"])
@login_required
def edit_staedtetrip(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
    
    return render_template("/bearbeiten_staedtetrip.html", reise=reise)

@reisen_bp.route("/edit_badeurlaub/<reise_id>", methods=["GET", "POST"])
@login_required
def edit_badeurlaub(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
    
    return render_template("/bearbeiten_badeurlaub.html", reise=reise)

@reisen_bp.route("/hinzufuegen_stopp/<reise_id>", methods=["GET", "POST"])
@login_required
def hinzufuegen_stopp(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Ungültige Reise-ID", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
   
    return render_template("hinzufuegen_stopp.html", reise=reise)

@reisen_bp.route("/hinzufuegen/<reise_id>/stopps", methods=["POST"])
@login_required
def hinzufuegen(reise_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'message': 'Keine oder ungültige JSON-Daten erhalten'}), 400

    neue_stopps = data.get('stopps')
    if not neue_stopps or not isinstance(neue_stopps, list):
        return jsonify({'message': 'Ungültige Stoppliste'}), 400

    try:
        oid = ObjectId(reise_id)
    except Exception:
        return jsonify({'message': 'Ungültige Reise-ID'}), 400

    reise = reisen.find_one({'_id': oid})
    if not reise:
        return jsonify({'message': 'Reise nicht gefunden'}), 404

    reisen.update_one({'_id': oid}, {'$set': {'stopps': neue_stopps}})

    return jsonify({'message': 'Stopp erfolgreich hinzugefügt'})

@reisen_bp.route("/entfernen/<reise_id>/stopp", methods=["POST"])
@login_required
def entferne_stopp(reise_id):
    data = request.get_json(silent=True)
    stopp_string = data.get('stopp')

    if not stopp_string:
        return jsonify({'message': 'Stopp erforderlich'}), 400

    try:
        oid = ObjectId(reise_id)
    except Exception:
        return jsonify({'message': 'Ungültige Reise-ID'}), 400

    reise = reisen.find_one({'_id': oid})
    if not reise:
        return jsonify({'message': 'Reise nicht gefunden'}), 404

    stopps = reise.get('stopps', [])

    if stopp_string not in stopps:
        return jsonify({'message': 'Stopp nicht gefunden'}), 404

    neuer_stopps = [s for s in stopps if s != stopp_string]

    reisen.update_one({'_id': oid}, {'$set': {'stopps': neuer_stopps}})

    return jsonify({'message': 'Stopp erfolgreich entfernt'})

@reisen_bp.route("/hinzufuegen_hotel/<reise_id>", methods=["GET", "POST"])
@login_required
def hinzufuegen_hotel(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Ungültige Reise-ID", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
   
    return render_template("hinzufuegen_hotel.html", reise=reise)

@reisen_bp.route('/reisen/<reise_id>/hotels', methods=['POST'])
def add_hotel_to_reise(reise_id):
    hotel = request.json

    if 'id' not in hotel:
        hotel['id'] = str(ObjectId())

    db.reisen.update_one(
        {'_id': ObjectId(reise_id)},
        {'$push': {'hotels': hotel}}
    )
    return jsonify({"message": "Hotel hinzugefügt", "id": hotel['id']}), 201

@reisen_bp.route('/reise/<reise_id>/remove_hotel/<hotel_id>', methods=['DELETE'])
@login_required
def remove_hotel(reise_id, hotel_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        return jsonify({"error": "Ungültige Reise-ID"}), 400

    result = db.reisen.update_one(
        {'_id': oid},
        {'$pull': {'hotels': {'id': hotel_id}}}
    )

    if result.modified_count == 0:
        return jsonify({"error": "Hotel nicht gefunden"}), 404

    return jsonify({"message": "Hotel entfernt"}), 200

@reisen_bp.route('/reisen/<reise_id>')
def show_reise_details(reise_id):
    reise = db.reisen.find_one({'_id': ObjectId(reise_id)})
    if not reise:
        return "Reise nicht gefunden", 404
    # Render Template, das z.B. Hotelliste mit Links zur Karte anzeigt
    # Hier nur Beispiel: JSON-Ausgabe
    return jsonify(reise)

@reisen_bp.route("/hinzufuegen_flug/<reise_id>", methods=["GET", "POST"])
@login_required
def hinzufuegen_flug(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Ungültige Reise-ID", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
   
    return render_template("hinzufuegen_flug.html", reise=reise)

@reisen_bp.route("/hinzufuegen_auto/<reise_id>", methods=["GET", "POST"])
@login_required
def hinzufuegen_auto(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Ungültige Reise-ID", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
   
    return render_template("hinzufuegen_auto.html", reise=reise)


@reisen_bp.route('/reise/<reise_id>/stopps', methods=['POST'])
def aktualisiere_stopps(reise_id):
    data = request.get_json()
    neue_stopps = data.get('stopps')

    if not neue_stopps or not isinstance(neue_stopps, list):
        return jsonify({'message': 'Ungültige Stoppliste'}), 400

    try:
        oid = ObjectId(reise_id)
    except Exception:
        return jsonify({'message': 'Ungültige Reise-ID'}), 400

    reise = reisen.find_one({'_id': oid})

    if not reise:
        return jsonify({'message': 'Reise nicht gefunden'}), 404

    reisen.update_one({'_id': oid}, {'$set': {'stopps': neue_stopps}})
    print("Neue Stopps gespeichert:", reisen.find_one({'_id': oid})['stopps'])

    return jsonify({'message': 'Stoppreihenfolge erfolgreich aktualisiert'})

@reisen_bp.route('/reise/<reise_id>/sehenswuerdigkeiten', methods=['POST'])
def aktualisiere_sehenswuerdigkeiten(reise_id):
    data = request.get_json()
    neue_sehenswuerdigkeiten = data.get('sehenswuerdigkeiten')

    if not neue_sehenswuerdigkeiten or not isinstance(neue_sehenswuerdigkeiten, list):
        return jsonify({'message': 'Ungültige SehenswürdigkeitenListe'}), 400

    try:
        oid = ObjectId(reise_id)
    except Exception:
        return jsonify({'message': 'Ungültige Reise-ID'}), 400

    reise = reisen.find_one({'_id': oid})

    if not reise:
        return jsonify({'message': 'Reise nicht gefunden'}), 404

    reisen.update_one({'_id': oid}, {'$set': {'sehenswuerdigkeiten': neue_sehenswuerdigkeiten}})

    return jsonify({'message': 'Sehenswürdigkeiten erfolgreich aktualisiert'})

@reisen_bp.route("/hinzufuegen_stopp_staedtetrip/<reise_id>", methods=["GET", "POST"])
@login_required
def hinzufuegen_stopp_staedtetrip(reise_id):
    try:
        oid = ObjectId(reise_id)
    except Exception:
        flash("Ungültige Reise-ID", "error")
        return redirect(url_for('reisen.dashboard'))
    
    reise = reisen.find_one({"_id": oid, "user_id": current_user.id})
    if not reise:
        flash("Reise nicht gefunden", "error")
        return redirect(url_for('reisen.dashboard'))
   
    return render_template("hinzufuegen_stopp_staedtetrip.html", reise=reise)

@reisen_bp.route("/hinzufuegen_staedtetrip/<reise_id>/stopps", methods=["POST"])
@login_required
def hinzufuegen_staedtetrip(reise_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'message': 'Keine oder ungültige JSON-Daten erhalten'}), 400

    neue_sehenswuerdigkeiten = data.get('sehenswuerdigkeiten')
    if not neue_sehenswuerdigkeiten or not isinstance(neue_sehenswuerdigkeiten, list):
        return jsonify({'message': 'Ungültige SehesnwürdigkeitenListe'}), 400

    try:
        oid = ObjectId(reise_id)
    except Exception:
        return jsonify({'message': 'Ungültige Reise-ID'}), 400

    reise = reisen.find_one({'_id': oid})
    if not reise:
        return jsonify({'message': 'Reise nicht gefunden'}), 404

    reisen.update_one({'_id': oid}, {'$set': {'sehenswuerdigkeiten': neue_sehenswuerdigkeiten}})

    return jsonify({'message': 'Sehenswürdigkeit erfolgreich hinzugefügt'})

@reisen_bp.route("/entfernen_staedtetrip/<reise_id>/stopp", methods=["POST"])
@login_required
def entferne_stopp_staedtetrip(reise_id):
    data = request.get_json(silent=True)
    sehenswuerdigkeiten_string = data.get('sehenswuerdigkeiten')

    if not sehenswuerdigkeiten_string:
        return jsonify({'message': 'Sehenswürdigkeit erforderlich'}), 400

    try:
        oid = ObjectId(reise_id)
    except Exception:
        return jsonify({'message': 'Ungültige Reise-ID'}), 400

    reise = reisen.find_one({'_id': oid})
    if not reise:
        return jsonify({'message': 'Reise nicht gefunden'}), 404

    sehenswuerdigkeiten = reise.get('sehenswurdigkeiten', [])

    if sehenswuerdigkeiten_string not in sehenswuerdigkeiten:
        return jsonify({'message': 'Sehenswürdigkeit nicht gefunden'}), 404

    neue_sehenswuerdigkeiten = [s for s in sehenswuerdigkeiten if s != sehenswuerdigkeiten_string]

    reisen.update_one({'_id': oid}, {'$set': {'sehenswuerdigkeiten': neue_sehenswuerdigkeiten}})

    return jsonify({'message': 'Sehenswürdigkeit erfolgreich entfernt'})

@reisen_bp.route("/reise/<reise_id>/bearbeiten", methods=["POST"])
@login_required
def bearbeiten_staedtetrip(reise_id):
    data = request.get_json()
    try:
        oid = ObjectId(reise_id)
    except Exception:
        return jsonify({'message': 'Ungültige Reise-ID'}), 400

    update_data = {}
    if 'anreise' in data:
        update_data['anreise'] = data['anreise']
    if 'abreise' in data:
        update_data['abreise'] = data['abreise']
    if 'sehenswuerdigkeiten' in data:
        update_data['sehenswuerdigkeiten'] = data['sehenswuerdigkeiten']
    if 'stopps' in data:
        update_data['stopps'] = data['stopps']
    if 'fluege' in data:
        update_data['fluege'] = data['fluege']
    if 'hotels' in data:
        update_data['hotels'] = data['hotels']

    result = reisen.update_one({'_id': oid}, {'$set': update_data})

    if result.modified_count == 1:
        return jsonify({'message': 'Reise erfolgreich aktualisiert'})
    else:
        return jsonify({'message': 'Keine Änderungen vorgenommen'}), 200








