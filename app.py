import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, User, DailyLog
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_very_secret_key_for_flask')

# Use Neon DB url if available, otherwise fallback to local sqlite
database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def get_today_str():
    return datetime.utcnow().strftime('%Y-%m-%d')

@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if action == 'register':
            user = User.query.filter_by(email=email).first()
            if user:
                flash('Email address already exists', 'error')
                return redirect(url_for('login'))
            
            new_user = User(email=email, password=generate_password_hash(password, method='scrypt'))
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for('dashboard'))
            
        elif action == 'login':
            user = User.query.filter_by(email=email).first()
            if not user or not check_password_hash(user.password, password):
                flash('Please check your login details and try again.', 'error')
                return redirect(url_for('login'))
            
            login_user(user)
            return redirect(url_for('dashboard'))
            
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    today_str = get_today_str()
    today_log = DailyLog.query.filter_by(user_id=current_user.id, date_str=today_str).first()
    
    if request.method == 'POST' and not today_log:
        done_today = request.form.get('done_today')
        assigned_work = request.form.get('assigned_work')
        
        new_log = DailyLog(
            date_str=today_str,
            done_today=done_today,
            assigned_work=assigned_work,
            user_id=current_user.id
        )
        db.session.add(new_log)
        db.session.commit()
        
        flash('Successfully submitted your daily log!', 'success')
        return redirect(url_for('dashboard'))

    past_logs = DailyLog.query.filter_by(user_id=current_user.id).order_by(DailyLog.timestamp.desc()).limit(10).all()
    
    return render_template('dashboard.html', 
                           is_submitted=bool(today_log),
                           past_logs=past_logs)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/cron/reminders', methods=['GET', 'POST'])
def cron_reminders():
    # Vercel sends an authorization header with the cron secret
    auth_header = request.headers.get('Authorization')
    expected_secret = os.environ.get('CRON_SECRET')
    
    if expected_secret and auth_header != f"Bearer {expected_secret}":
        return jsonify({"error": "Unauthorized"}), 401
        
    today_str = get_today_str()
    users = User.query.all()
    reminders_sent = 0
    for user in users:
        log = DailyLog.query.filter_by(user_id=user.id, date_str=today_str).first()
        if not log:
            print(f"[NOTIFICATION] Reminder for {user.email}: You haven't submitted your daily log yet!")
            reminders_sent += 1
            # Actual email/webhook logic would go here
            
    return jsonify({"success": True, "reminders_sent": reminders_sent})

# Ensure tables are created 
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
