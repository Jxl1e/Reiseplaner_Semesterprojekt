from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import UserMixin, login_user, logout_user, current_user, login_required
from bson.objectid import ObjectId
from app import db, reisen, bcrypt, login_manager

auth_bp = Blueprint("auth", __name__)

users = db["users"]

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["_id"])
        self.email = user_data["email"]

@login_manager.user_loader
def load_user(user_id):
    user = users.find_one({"_id": ObjectId(user_id)})
    return User(user) if user else None

@auth_bp.context_processor
def inject_user():
    return dict(current_user=current_user)

@login_manager.user_loader
def load_user(user_id):
    user = users.find_one({"_id":ObjectId(user_id)})
    return User(user) if user else None

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = users.find_one({"email": request.form["email"]})
        if user and bcrypt.check_password_hash(user["password"], request.form["password"]):
            login_user(User(user))
            flash("Login erfolgreich. Willkommen zurück!", "success")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('reisen.dashboard'))
        else:
            flash("Login fehlgeschlagen. Bitte erneut versuchen", "error")
    return render_template('login.html')      

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        hashed_pw = bcrypt.generate_password_hash(request.form["password"]).decode('utf-8')
        email = request.form["email"]

        users.insert_one({"email": request.form["email"], "password": hashed_pw})

        user = users.find_one({"email": email})
        login_user(User(user)) 

        flash("Registrierung erfolgreich. Willkommen!", "success")
        return redirect(url_for('reisen.initial_dashboard'))
    return render_template('register.html')

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Erfolgreich ausgeloggt.", "success")  
    return redirect(url_for('reisen.index'))

