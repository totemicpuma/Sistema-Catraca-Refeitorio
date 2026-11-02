from flask import Flask
import os
import secrets
from flask_sqlalchemy import SQLAlchemy

from models import db
from utils import inject_theme

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)

app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "refeitorio.db")
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
app.config['SESSION_PERMANENT'] = False

db.init_app(app)

app.context_processor(inject_theme)

from routes import configure_routes
configure_routes(app, db)

with app.app_context():
    db.create_all()
