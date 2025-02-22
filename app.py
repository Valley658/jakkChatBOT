from flask import Flask, render_template, redirect, url_for, request, send_from_directory, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from forms import LoginForm, RegistrationForm, LanguageForm, ChatForm
from chatbot import get_response, get_available_models
import os
import base64
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import psutil
import pyttsx3
import hashlib
import tensorflow as tf
from itsdangerous import URLSafeTimedSerializer
import openai

app = Flask(__name__)

def generate_secret_key():
    return base64.b64encode(os.urandom(24)).decode('utf-8')

app.config['SECRET_KEY'] = generate_secret_key()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data_database.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['COOKIE_SECRET'] = generate_secret_key()
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Serializer for cookies
serializer = URLSafeTimedSerializer(app.config['COOKIE_SECRET'])

# Lazy load TensorFlow configuration to optimize startup time
def configure_tensorflow():
    import tensorflow as tf
    # Suppress TensorFlow logging
    tf.get_logger().setLevel('ERROR')
    physical_devices = tf.config.list_physical_devices('GPU')
    if physical_devices:
        try:
            # Set memory growth for each GPU
            for gpu in physical_devices:
                tf.config.experimental.set_memory_growth(gpu, True)
            # Set the default GPU to GPU 0
            tf.config.experimental.set_visible_devices(physical_devices[0], 'GPU')
        except RuntimeError as e:
            print(e)
    else:
        print("No GPU devices found.")

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def set_username(self, username):
        self.username = hashlib.sha256(username.encode()).hexdigest()

class UserCookie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cookie_data = db.Column(db.String(500), nullable=False)

class UserLanguage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    computer_name = db.Column(db.String(150), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    error_message = None
    if form.validate_on_submit():
        user = User.query.filter_by(username=hashlib.sha256(form.username.data.encode()).hexdigest()).first()
        if user is None:
            error_message = "Username or password does not exist."
        elif not user.check_password(form.password.data):
            error_message = "Incorrect password."
        else:
            login_user(user)
            
            # Automatically detect system language
            system_language = os.getenv('LANG', 'en').split('.')[0]
            computer_name = os.getenv('COMPUTERNAME', 'Unknown')
            
            # Save language selection to the database
            user_language = UserLanguage(user_id=current_user.id, language=system_language, computer_name=computer_name)
            db.session.add(user_language)
            db.session.commit()

            if current_user.username == hashlib.sha256('admin'.encode()).hexdigest():
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('chat', language=system_language))
    return render_template('login.html', form=form, error_message=error_message, css_url=url_for('static', filename='style.css'))

# Add memory feature for chatbot
chat_memory = {}

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    form = ChatForm()
    language = request.args.get('language')
    if not language:
        user_language = UserLanguage.query.filter_by(user_id=current_user.id).order_by(UserLanguage.id.desc()).first()
        language = user_language.language if user_language else 'en'
    if form.validate_on_submit():
        user_input = form.message.data
        model = form.model.data if form.model.data else 'default-model'  # Fix model selection issue
        user_id = current_user.id
        if user_id not in chat_memory:
            chat_memory[user_id] = []
        chat_memory[user_id].append(user_input)
        
        # Use ChatGPT API
        bot_response = get_response(user_input, model)
        
        # Use pyttsx3 for TTS
        engine = pyttsx3.init()
        engine.save_to_file(bot_response, 'static/response.wav')
        engine.runAndWait()
        
        return render_template('chat.html', form=form, user_input=user_input, bot_response=bot_response, css_url=url_for('static', filename='style.css'), audio_url=url_for('static', filename='response.wav'))
    return render_template('chat.html', form=form, css_url=url_for('static', filename='style.css'))

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('chat'))
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('chat'))
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        flash('File successfully uploaded')
        return redirect(url_for('chat'))

# Add GPU and CPU usage monitoring
@app.route('/system_status')
@login_required
def system_status():
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_info = psutil.virtual_memory()
    gpu_devices = tf.config.list_physical_devices('GPU')
    gpu_usage = [tf.config.experimental.get_memory_info(gpu)['current'] for gpu in gpu_devices] if gpu_devices else []
    status = "Normal" if cpu_usage < 80 and memory_info.percent < 80 else "Warning" if cpu_usage < 90 and memory_info.percent < 90 else "Critical"
    return jsonify(cpu_usage=cpu_usage, memory_info=memory_info._asdict(), gpu_usage=gpu_usage, status=status)

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.username == hashlib.sha256('admin'.encode()).hexdigest():
        users = User.query.all()
        user_languages = UserLanguage.query.all()
        memory_info = psutil.virtual_memory()  # Add this line to get memory info
        status = "Normal"  # Define the status variable
        return render_template('dashboard.html', users=users, user_languages=user_languages, css_url=url_for('static', filename='style.css'), status=status, memory_info=memory_info)
    return redirect(url_for('chat'))

@app.route('/admin_panel')
@login_required
def admin_panel():
    if current_user.username == hashlib.sha256('admin'.encode()).hexdigest():
        return render_template('admin_panel.html', css_url=url_for('static', filename='style.css'))
    return redirect(url_for('chat'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=hashlib.sha256(form.username.data.encode()).hexdigest())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html', form=form, css_url=url_for('static', filename='style.css'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
def index():
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create admin account if it doesn't exist
        if not User.query.filter_by(username=hashlib.sha256('admin'.encode()).hexdigest()).first():
            admin = User()
            admin.set_username('admin')
            admin.set_password('reewskali15@gm')
            db.session.add(admin)
            db.session.commit()
    configure_tensorflow()
    app.run(host='0.0.0.0', port=5000)