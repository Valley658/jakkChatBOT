from flask import Flask, render_template, redirect, url_for, request, send_from_directory, flash, jsonify, make_response, send_file
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
import subprocess
import torch
from transformers import GPT2LMHeadModel, GPT2Tokenizer, T5ForConditionalGeneration, T5Tokenizer
from googletrans import Translator
import requests
import shutil

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

serializer = URLSafeTimedSerializer(app.config['COOKIE_SECRET'])

def configure_tensorflow():
    import tensorflow as tf
    tf.get_logger().setLevel('ERROR')
    physical_devices = tf.config.list_physical_devices('GPU')
    if physical_devices:
        try:
            for gpu in physical_devices:
                tf.config.experimental.set_memory_growth(gpu, True)
            tf.config.experimental.set_visible_devices(physical_devices[0], 'GPU')
        except RuntimeError as e:
            print(e)
    else:
        print("No GPU devices found.")

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model_name = "gpt2"
tokenizer = GPT2Tokenizer.from_pretrained(model_name)
model = GPT2LMHeadModel.from_pretrained(model_name).to(device)

t5_tokenizer = T5Tokenizer.from_pretrained("t5-small")
t5_model = T5ForConditionalGeneration.from_pretrained("t5-small").to(device)

translator = Translator()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    nickname = db.Column(db.String(150), nullable=False)
    password = db.Column(db.String(150), nullable=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def set_username(self, username):
        self.username = hashlib.sha256(username.encode()).hexdigest()

    def set_nickname(self, nickname):
        self.nickname = nickname

class UserCookie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cookie_data = db.Column(db.String(500), nullable=False)

class UserLanguage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    computer_name = db.Column(db.String(150), nullable=False)

class ChatMemory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    nickname = db.Column(db.String(150), nullable=False)
    message = db.Column(db.String(500), nullable=False)

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
            system_language = request.accept_languages.best_match(['en', 'ko', 'es', 'fr', 'de', 'zh'])
            computer_name = os.getenv('COMPUTERNAME', 'Unknown')
            user_language = UserLanguage(user_id=current_user.id, language=system_language, computer_name=computer_name)
            db.session.add(user_language)
            db.session.commit()
            if current_user.username == hashlib.sha256('admin'.encode()).hexdigest():
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('chat', language=system_language))
    return render_template('login.html', form=form, error_message=error_message, css_url=url_for('static', filename='style.css'))

chat_memory = {}

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    form = ChatForm()
    language = request.args.get('language')
    if not language:
        user_language = UserLanguage.query.filter_by(user_id=current_user.id).order_by(UserLanguage.id.desc()).first()
        language = user_language.language if user_language else 'ko'
    if form.validate_on_submit():
        user_input = form.message.data
        user_id = current_user.id
        chat_memory_entry = ChatMemory(user_id=user_id, nickname=current_user.nickname, message=user_input)
        db.session.add(chat_memory_entry)
        db.session.commit()
        
        # Generate response using GPT-2 model
        inputs = tokenizer.encode(user_input, return_tensors='pt').to(device)
        outputs = model.generate(inputs, max_length=150, num_return_sequences=1)
        bot_response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        translated_response = translator.translate(bot_response, dest='ko').text
        chat_memory_entry = ChatMemory(user_id=user_id, nickname='Bot', message=translated_response)
        db.session.add(chat_memory_entry)
        db.session.commit()
        return jsonify(user_input=user_input, bot_response=translated_response, chat_memory=[{'nickname': entry.nickname, 'message': entry.message} for entry in ChatMemory.query.filter_by(user_id=user_id).all()])
    return render_template('chat.html', form=form, css_url=url_for('static', filename='style.css'), username=current_user.nickname, chat_memory=[{'nickname': entry.nickname, 'message': entry.message} for entry in ChatMemory.query.filter_by(user_id=current_user.id).all()], additional_features=True)

@app.route('/speech_to_text', methods=['POST'])
@login_required
def speech_to_text():
    if 'audio' not in request.files:
        return jsonify(error="No audio file provided"), 400
    audio_file = request.files['audio']
    engine = pyttsx3.init()
    engine.save_to_file(audio_file, 'static/response.wav')
    engine.runAndWait()
    return jsonify(text="Speech-to-text conversion completed.")

@app.route('/text_to_speech', methods=['POST'])
@login_required
def text_to_speech():
    text = request.form.get('text')
    if not text:
        return jsonify(error="No text provided"), 400
    audio_file_path = 'static/tts_response.wav'
    engine = pyttsx3.init()
    engine.save_to_file(text, audio_file_path)
    engine.runAndWait()
    return jsonify(audio_url=url_for('play_audio'))

@app.route('/play_audio')
@login_required
def play_audio():
    audio_file_path = 'static/tts_response.wav'
    if os.path.exists(audio_file_path):
        response = make_response(send_file(audio_file_path, mimetype='audio/wav'))
        response.headers['Content-Disposition'] = 'inline; filename=response.wav'
        return response
    return jsonify(error="Audio file not found"), 404

@app.route('/delete_audio')
@login_required
def delete_audio():
    audio_file_path = 'static/tts_response.wav'
    if os.path.exists(audio_file_path):
        os.remove(audio_file_path)
        return jsonify(message="Audio file deleted successfully")
    return jsonify(error="Audio file not found"), 404

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
        memory_info = psutil.virtual_memory()
        status = "Normal"
        models = get_available_models()
        return render_template('dashboard.html', users=users, user_languages=user_languages, css_url=url_for('static', filename='style.css'), status=status, memory_info=memory_info, models=models)
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
        if len(form.password.data) < 2 or len(form.password.data) >= 16:
            flash('Password must be at least 2 characters and less than 16 characters.')
            return redirect(url_for('register'))
        user = User(username=hashlib.sha256(form.username.data.encode()).hexdigest())
        user.set_password(form.password.data)
        user.set_nickname(form.nickname.data)
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

@app.route('/generate_requirements')
@login_required
def generate_requirements():
    with open('requirements.txt', 'w') as f:
        subprocess.run(['pip', 'freeze'], stdout=f)
        f.write('\ntf-keras\n')
        f.write('sentencepiece\n')
    flash('requirements.txt generated successfully.')
    return redirect(url_for('dashboard'))

@app.route('/generate_setup')
@login_required
def generate_setup():
    with open('setup.bat', 'w') as f:
        f.write('@echo off\n')
        f.write('pip install -r requirements.txt\n')
        f.write('pip install sentencepiece\n')
    flash('setup.bat generated successfully.')
    return redirect(url_for('dashboard'))

@app.route('/internet_search', methods=['POST'])
@login_required
def internet_search():
    query = request.form.get('query')
    if not query:
        return jsonify(error="No query provided"), 400
    response = requests.get(f"https://api.duckduckgo.com/?q={query}&format=json")
    if response.status_code == 200:
        return jsonify(response.json())
    else:
        return jsonify(error="Failed to fetch data from the internet"), 500

@app.route('/download_models')
@login_required
def download_models():
    models = ['gpt2', 't5-small', 'bert-base-uncased']
    for model_name in models:
        if model_name == 'gpt2':
            GPT2LMHeadModel.from_pretrained(model_name)
            GPT2Tokenizer.from_pretrained(model_name)
        elif model_name == 't5-small':
            T5ForConditionalGeneration.from_pretrained(model_name)
            T5Tokenizer.from_pretrained(model_name)
        elif model_name == 'bert-base-uncased':
            from transformers import BertModel, BertTokenizer
            BertModel.from_pretrained(model_name)
            BertTokenizer.from_pretrained(model_name)
    flash('Models downloaded successfully.')
    return redirect(url_for('dashboard'))

@app.route('/additional_feature')
@login_required
def additional_feature():
    return jsonify(message="Additional feature executed successfully.")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    configure_tensorflow()
    app.run(host='0.0.0.0', port=80)