import os
import random
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import logging
from datetime import datetime, timedelta
from functools import wraps
import requests
from twilio.rest import Client
import json
import re

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Database initialization
db = SQLAlchemy(app)

# Login manager initialization
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Mail configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
mail = Mail(app)

# Twilio configuration
TWILIO_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
twilio_client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

# Logging configuration
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    phone_verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(6), nullable=True)
    # Add relationship to chat messages
    messages = db.relationship('ChatMessage', backref='user', lazy=True)

# Chat message model
class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Add this function before the routes
def get_bot_response(message):
    # Convert message to lowercase for easier matching
    message = message.lower()
    
    # DOJ-specific response patterns
    patterns = {
        r'hello|hi|hey': 'Hello! I\'m the Department of Justice Assistant. How can I help you today?',
        r'what is doj|what is department of justice': 'The Department of Justice (DOJ) is the federal executive department responsible for enforcing federal laws and administering justice in the United States. It is equivalent to the justice or interior ministries of other countries.',
        r'what does doj do|what are doj responsibilities': 'The DOJ is responsible for:\n- Enforcing federal laws\n- Representing the U.S. in legal matters\n- Ensuring public safety\n- Protecting civil rights\n- Combating crime and terrorism',
        r'contact|how to contact|reach out': 'You can contact the Department of Justice through:\n- Main Switchboard: (202) 514-2000\n- TTY: (202) 514-1888\n- Website: www.justice.gov',
        r'file complaint|report crime|report incident': 'To file a complaint or report a crime:\n1. For civil rights violations: civilrights.justice.gov\n2. For fraud: fraud.ojp.gov\n3. For general crimes: tips.fbi.gov',
        r'job|career|employment|work at doj': 'For DOJ career opportunities:\n- Visit: www.justice.gov/careers\n- Check USAJobs.gov for current openings\n- Contact the Office of Attorney Recruitment and Management',
        r'press release|news|updates': 'For DOJ press releases and news:\n- Visit: www.justice.gov/news\n- Subscribe to DOJ newsletters\n- Follow DOJ on social media',
        r'freedom of information|foia': 'For FOIA requests:\n- Visit: www.justice.gov/oip\n- Submit requests through FOIA.gov\n- Contact the FOIA office at (202) 514-3642',
        r'help|what can you do': 'I can help you with:\n- General information about DOJ\n- Filing complaints\n- Contact information\n- Career opportunities\n- Press releases and news\n- FOIA requests\nJust ask me anything!',
        r'thank you|thanks': 'You\'re welcome! Is there anything else I can help you with?',
        r'bye|goodbye': 'Thank you for contacting the Department of Justice. Have a great day!'
    }
    
    # Check for time-related questions
    if re.search(r'time|current time', message):
        return f"The current time is {datetime.now().strftime('%H:%M:%S')}"
    
    # Check for date-related questions
    if re.search(r'date|today', message):
        return f"Today's date is {datetime.now().strftime('%Y-%m-%d')}"
    
    # Check patterns
    for pattern, response in patterns.items():
        if re.search(pattern, message):
            return response
    
    # Default response
    return "I'm not sure about that specific information. Please try asking about DOJ's general responsibilities, filing complaints, contact information, or career opportunities. How else can I help you?"

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        phone = request.form.get('phone')

        # Input validation
        if not username or not password or not email or not phone:
            flash('All fields are required')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))

        # Generate verification code
        verification_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        # Create new user
        hashed_password = generate_password_hash(password)
        user = User(
            username=username,
            password=hashed_password,
            email=email,
            phone=phone,
            verification_code=verification_code
        )
        db.session.add(user)
        db.session.commit()

        logger.info(f'New user registered: {email}')
        flash(f'Registration successful! Your verification code is: {verification_code}')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/verify-email/<token>')
def verify_email(token):
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.filter_by(email=data['email']).first()
        if user:
            user.email_verified = True
            db.session.commit()
            logger.info(f'Email verified for user: {user.email}')
            flash('Email verified successfully')
        return redirect(url_for('login'))
    except:
        flash('Invalid or expired verification link')
        return redirect(url_for('login'))

@app.route('/verify-phone', methods=['POST'])
@login_required
def verify_phone():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    code = request.form.get('code')
    if code == current_user.verification_code:
        current_user.phone_verified = True
        db.session.commit()
        logger.info(f'Phone verified for user: {current_user.email}')
        flash('Phone verified successfully')
    else:
        flash('Invalid verification code')
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            logger.info(f'User logged in: {user.email}')
            flash('Logged in successfully!')
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!')
    return redirect(url_for('index'))

@app.route('/sso/google')
def google_login():
    # Google OAuth2 implementation
    return redirect(url_for('dashboard'))

@app.route('/sso/facebook')
def facebook_login():
    # Facebook OAuth2 implementation
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=current_user.username, phone_verified=current_user.phone_verified)

@app.route('/backup')
@login_required
def backup():
    # Create backup of the database
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'backups/backup_{timestamp}.db'
    os.makedirs('backups', exist_ok=True)
    with open(backup_path, 'w') as f:
        for user in User.query.all():
            f.write(f"{user.email},{user.phone}\n")
    logger.info(f'Backup created: {backup_path}')
    return jsonify({'message': 'Backup created successfully'})

@app.route('/chatbot')
@login_required
def chatbot():
    if not current_user.phone_verified:
        flash('Please verify your phone number first')
        return redirect(url_for('dashboard'))
    # Get chat history
    chat_history = ChatMessage.query.filter_by(user_id=current_user.id).order_by(ChatMessage.timestamp.desc()).limit(10).all()
    chat_history = reversed(chat_history)  # Show messages in chronological order
    return render_template('chatbot.html', username=current_user.username, chat_history=chat_history)

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    if not current_user.phone_verified:
        return jsonify({'response': 'Please verify your phone number first'})
    
    data = request.get_json()
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({'response': 'Please send a message!'})
    
    # Get bot response
    bot_response = get_bot_response(user_message)
    
    # Save the message to database
    chat_message = ChatMessage(
        user_id=current_user.id,
        message=user_message,
        response=bot_response
    )
    db.session.add(chat_message)
    db.session.commit()
    
    # Log the chat message
    logger.info(f'Chat message from {current_user.username}: {user_message}')
    
    return jsonify({'response': bot_response})

if __name__ == '__main__':
    # Create database tables
    with app.app_context():
        db.create_all()  # Create new tables
    app.run(debug=True)
