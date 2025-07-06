from flask import Flask
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from pymongo import MongoClient
from flask_assets import Environment

API_KEY = "Gsbuy4IeGweWPquMj4z8i8sISSjGli2z"
API_SECRET = "75Ocnq4Z3Fn7ExTc"
GOOGLE_API_KEY = "AIzaSyClEWrPjwpVkTYTXU2yhI2AN7QJ1LYGzHM"


app = Flask(__name__)
app.secret_key = "geheimes_token"

client = MongoClient("mongodb+srv://TestUser:Kovk53DlSe0lxSSK@reiseplaner.sj6kir6.mongodb.net/?retryWrites=true&w=majority&appName=Reiseplaner")
db = client["reiseplaner"]
users = db["users"]
reisen = db["reisen"]
hotels_collection = db['hotels']

bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
assets = Environment(app)

from auth import auth_bp
from reisen import reisen_bp
from api import api_bp

app.register_blueprint(auth_bp)
app.register_blueprint(reisen_bp)
app.register_blueprint(api_bp)

print("Registrierte Routen:")
for rule in app.url_map.iter_rules():
    print(rule)

if __name__ == "__main__":
    app.run(debug=True)


   