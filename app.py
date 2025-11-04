from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date
from wtforms import StringField, PasswordField, SubmitField, SelectField, DateField, FloatField
from wtforms.validators import DataRequired, Email
from io import BytesIO
import csv
import os
from PIL import Image

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-2025-change-in-prod'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hotel.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(10), unique=True, nullable=False)
    room_type = db.Column(db.String(50), nullable=False)
    price_per_night = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Available')
    image_file = db.Column(db.String(100), default='default.jpg')

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guest_name = db.Column(db.String(100), nullable=False)
    guest_email = db.Column(db.String(100), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    check_in = db.Column(db.Date, nullable=False)
    check_out = db.Column(db.Date, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Booked')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Seed data
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@hotel.com', password_hash=generate_password_hash('admin123'), is_admin=True)
        db.session.add(admin)
        db.session.commit()
    if Room.query.count() == 0:
        default_img = os.path.join(app.config['UPLOAD_FOLDER'], 'default.jpg')
        if not os.path.exists(default_img):
            # Create a simple default image
            img = Image.new('RGB', (200, 150), color='lightblue')
            img.save(default_img)
        rooms = [
            Room(number='101', room_type='Single', price_per_night=100.0, image_file='default.jpg'),
            Room(number='102', room_type='Double', price_per_night=150.0, image_file='default.jpg'),
            Room(number='201', room_type='Suite', price_per_night=250.0, image_file='default.jpg')
        ]
        db.session.bulk_save_objects(rooms)
        db.session.commit()

# Forms
from flask_wtf import FlaskForm
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Register')

class RoomForm(FlaskForm):
    number = StringField('Room Number', validators=[DataRequired()])
    room_type = StringField('Type', validators=[DataRequired()])
    price = FloatField('Price/Night', validators=[DataRequired()])
    status = SelectField('Status', choices=[('Available', 'Available'), ('Occupied', 'Occupied'), ('Maintenance', 'Maintenance')])
    submit = SubmitField('Save')

class BookingForm(FlaskForm):
    guest_name = StringField('Guest Name', validators=[DataRequired()])
    guest_email = StringField('Email', validators=[DataRequired(), Email()])
    room_id = SelectField('Room', coerce=int)
    check_in = DateField('Check-in', format='%Y-%m-%d', validators=[DataRequired()])
    check_out = DateField('Check-out', format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Book')

# Routes
@app.route('/')
@login_required
def dashboard():
    total_rooms = Room.query.count()
    available_rooms = Room.query.filter_by(status='Available').count()
    occupancy = (total_rooms - available_rooms) / total_rooms * 100 if total_rooms > 0 else 0
    bookings_data = [b.check_in for b in Booking.query.filter_by(status='Booked').order_by(Booking.check_in).limit(7).all()]  # For chart
    return render_template('dashboard.html', occupancy=occupancy, bookings_data=bookings_data)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials!', 'danger')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username taken!', 'danger')
        elif User.query.filter_by(email=form.email.data).first():
            flash('Email taken!', 'danger')
        else:
            user = User(username=form.username.data, email=form.email.data, password_hash=generate_password_hash(form.password.data))
            db.session.add(user)
            db.session.commit()
            flash('Registered! Please login.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/rooms', methods=['GET', 'POST'])
@login_required
def rooms():
    form = RoomForm()
    if form.validate_on_submit():
        # Handle image upload if added later
        room = Room(number=form.number.data, room_type=form.room_type.data, price_per_night=form.price.data, status=form.status.data)
        db.session.add(room)
        db.session.commit()
        flash('Room added!', 'success')
        return redirect(url_for('rooms'))
    rooms_list = Room.query.all()
    return render_template('rooms.html', rooms=rooms_list, form=form)

@app.route('/edit_room/<int:room_id>', methods=['POST'])
@login_required
def edit_room(room_id):
    room = Room.query.get_or_404(room_id)
    form = RoomForm(obj=room)
    if form.validate_on_submit():
        room.number = form.number.data
        room.room_type = form.room_type.data
        room.price_per_night = form.price.data
        room.status = form.status.data
        db.session.commit()
        flash('Updated!', 'success')
    return redirect(url_for('rooms'))

@app.route('/delete_room/<int:room_id>')
@login_required
def delete_room(room_id):
    room = Room.query.get_or_404(room_id)
    if Booking.query.filter_by(room_id=room_id).first():
        flash('Active booking blocks deletion!', 'warning')
    else:
        db.session.delete(room)
        db.session.commit()
        flash('Deleted!', 'success')
    return redirect(url_for('rooms'))

@app.route('/bookings', methods=['GET', 'POST'])
@login_required
def bookings():
    form = BookingForm()
    available_rooms = [(r.id, f"{r.number} ({r.room_type}) - ${r.price_per_night}") for r in Room.query.filter_by(status='Available').all()]
    form.room_id.choices = available_rooms
    search = request.args.get('search', '')
    bookings_list = Booking.query.filter(
        (Booking.guest_name.contains(search)) | (Booking.guest_email.contains(search))
    ).all()
    if form.validate_on_submit():
        room = Room.query.get(form.room_id.data)
        nights = (form.check_out.data - form.check_in.data).days
        total = room.price_per_night * nights
        booking = Booking(guest_name=form.guest_name.data, guest_email=form.guest_email.data,
                          room_id=form.room_id.data, check_in=form.check_in.data, check_out=form.check_out.data,
                          total_amount=total)
        room.status = 'Occupied'
        db.session.add(booking)
        db.session.commit()
        # Sim email
        print(f"Email sent to {form.guest_email.data}: Booking confirmed!")
        flash('Booked! Email sent.', 'success')
        return redirect(url_for('bookings'))
    return render_template('bookings.html', bookings=bookings_list, form=form, search=search)

@app.route('/check_in/<int:booking_id>')
@login_required
def check_in(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.status == 'Booked':
        booking.status = 'Checked In'
        db.session.commit()
        flash('Checked in!', 'success')
    return redirect(url_for('bookings'))

@app.route('/check_out/<int:booking_id>')
@login_required
def check_out(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.status in ['Booked', 'Checked In']:
        booking.status = 'Checked Out'
        room = Room.query.get(booking.room_id)
        room.status = 'Available'
        db.session.commit()
        flash(f'Checked out! Total: ${booking.total_amount}', 'info')
    return redirect(url_for('bookings'))

@app.route('/export_bookings')
@login_required
def export_bookings():
    bookings = Booking.query.all()
    si = BytesIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Guest', 'Email', 'Room', 'Check-in', 'Check-out', 'Total', 'Status'])
    for b in bookings:
        cw.writerow([b.id, b.guest_name, b.guest_email, b.room.number, b.check_in, b.check_out, b.total_amount, b.status])
    si.seek(0)
    return send_file(si, mimetype='text/csv', as_attachment=True, download_name='bookings.csv')

@app.route('/users')
@login_required
def users():
    if not current_user.is_admin:
        flash('Admin only!', 'danger')
        return redirect(url_for('dashboard'))
    users_list = User.query.all()
    return render_template('users.html', users=users_list)

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)
