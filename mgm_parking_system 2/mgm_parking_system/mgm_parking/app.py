from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mysqldb import MySQL
import hashlib
import os
import re
import time
from datetime import datetime, date
import random
import string
import threading
import subprocess

def send_automatic_alert(booking_data):
    """
    Simulates a background Bank SMS by displaying a Native Windows Notification
    and logging to the console. This runs in a separate thread.
    """
    try:
        phone = booking_data.get('phone', 'your mobile')
        title = f"💬 SMS sent to {phone}"
        
        dur_mins = booking_data.get('duration', 0)
        h = dur_mins // 60
        m = dur_mins % 60
        dur_str = f"{h}h" if h > 0 else ""
        if m > 0: dur_str += f" {m}m"
        dur_str = dur_str.strip()

        msg = (
            f"Your Booking Token`n"
            f"{booking_data['token']}`n"
            f"📍 {booking_data['zone']} — Slot {booking_data['slot_number']} • {booking_data['booking_date']}`n"
            f"⏰ {booking_data['time_slot']} → {booking_data['end_time']} ({dur_str}) • Show at campus gate"
        )
        
        # PowerShell script to show a Windows Balloon Tip notification natively
        ps_script = f"""
        Add-Type -AssemblyName System.Windows.Forms
        $notify = New-Object System.Windows.Forms.NotifyIcon
        $notify.Icon = [System.Drawing.SystemIcons]::Information
        $notify.Visible = $true
        $notify.ShowBalloonTip(10000, '{title}', '{msg}', [System.Windows.Forms.ToolTipIcon]::None)
        """
        # Run powershell without showing a window
        subprocess.run(["powershell", "-WindowStyle", "Hidden", "-Command", ps_script], capture_output=True)
        print(f"\n[BACKGROUND ALERT SENT] -> {msg.replace('`n', ' | ')}\n")
    except Exception as e:
        print(f"Failed to send background alert: {e}")

app = Flask(__name__)
app.secret_key = 'mgm_parking_secret_2024'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 1 day in seconds

# ─── MySQL Config (XAMPP) ────────────────────────────────────────────────────
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''   # default XAMPP password
app.config['MYSQL_DB'] = 'mgm_parking'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)


@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response



def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def time_to_minutes(t_str):
    try:
        h, m = map(int, t_str.split(':'))
        return h * 60 + m
    except Exception:
        return 0


def minutes_to_time(mins):
    h = mins // 60
    m = mins % 60
    return f"{str(h).zfill(2)}:{str(m).zfill(2)}"


def format_time_12hr(mins):
    h = mins // 60
    m = mins % 60
    ampm = "AM" if h < 12 else "PM"
    h_12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
    return f"{h_12}:{str(m).zfill(2)} {ampm}"


def update_slot_statuses(cur):
    now = datetime.now()
    current_date = now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M')
    
    # Auto-complete expired bookings
    cur.execute("""
        UPDATE bookings 
        SET status = 'completed', end_time = %s 
        WHERE status = 'active' 
          AND (booking_date < %s OR (booking_date = %s AND end_time_slot <= %s))
    """, (now.strftime('%Y-%m-%d %H:%M:%S'), current_date, current_date, current_time))
    
    # Auto-cancel bookings that started more than 15 minutes ago and are not checked in
    current_mins = now.hour * 60 + now.minute
    
    # 1. Past dates cleanup: cancel active, unchecked-in bookings from past dates
    cur.execute("""
        UPDATE bookings 
        SET status = 'cancelled', end_time = %s 
        WHERE status = 'active' AND checked_in = 0 AND booking_date < %s
    """, (now.strftime('%Y-%m-%d %H:%M:%S'), current_date))
    
    # 2. Today's bookings: cancel if start time + 15 mins is in the past
    cur.execute("""
        SELECT id, time_slot 
        FROM bookings 
        WHERE status = 'active' AND checked_in = 0 AND booking_date = %s
    """, (current_date,))
    today_active_no_checkin = cur.fetchall()
    
    for b in today_active_no_checkin:
        b_start_mins = time_to_minutes(b['time_slot'])
        if current_mins >= b_start_mins + 15:
            cur.execute("""
                UPDATE bookings 
                SET status = 'cancelled', end_time = %s 
                WHERE id = %s
            """, (now.strftime('%Y-%m-%d %H:%M:%S'), b['id']))
    
    # Find all slots that have an active booking right now (or checked-in early)
    cur.execute("""
        SELECT DISTINCT slot_id 
        FROM bookings 
        WHERE status = 'active' 
          AND booking_date = %s 
          AND (
            (%s >= time_slot AND %s < end_time_slot)
            OR (checked_in = 1 AND %s < end_time_slot)
          )
    """, (current_date, current_time, current_time, current_time))
    active_slot_ids = [row['slot_id'] for row in cur.fetchall()]
    
    # Sync status in database
    if active_slot_ids:
        format_strings = ','.join(['%s'] * len(active_slot_ids))
        cur.execute(f"""
            UPDATE parking_slots 
            SET status = 'occupied' 
            WHERE id IN ({format_strings}) AND status IN ('available', 'occupied')
        """, tuple(active_slot_ids))
        
        cur.execute(f"""
            UPDATE parking_slots 
            SET status = 'available' 
            WHERE id NOT IN ({format_strings}) AND status IN ('available', 'occupied')
        """, tuple(active_slot_ids))
    else:
        cur.execute("""
            UPDATE parking_slots 
            SET status = 'available' 
            WHERE status IN ('available', 'occupied')
        """)


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Session expired. Please login again', 'toast_type': 'warning'})
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ─── Auth Routes ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'success': False, 'message': 'Please fill all fields'})

        # Email format check
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            return jsonify({'success': False, 'message': 'Please enter a valid email address'})

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()

        if user and user['password'] == hash_password(password):
            session.permanent = True
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['user_email'] = user['email']
            session['vehicle_no'] = user['vehicle_no']
            session['vehicle_type'] = user['vehicle_type']
            session['role'] = user['role']
            return jsonify({'success': True, 'message': 'Login successful'})
        return jsonify({'success': False, 'message': 'Invalid email or password'})

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        data = request.get_json()
        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        vehicle_no = data.get('vehicle_no', '').strip().upper()
        phone = data.get('phone', '').strip()
        department = data.get('department', '').strip()
        vehicle_type = data.get('vehicle_type', 'two_wheeler').strip()
        role = 'faculty' if data.get('department', '') in ('Faculty', 'Staff') else 'student'

        # Check required fields
        if not all([full_name, email, password, vehicle_no, phone, department, vehicle_type]):
            return jsonify({'success': False, 'message': 'Please fill all required fields'})

        # Name validation: min 3 chars, letters and space only
        name_regex = r'^[a-zA-Z\s]{3,50}$'
        if not re.match(name_regex, full_name):
            return jsonify({'success': False, 'message': 'Name must be at least 3 letters, containing only alphabets'})

        # Email validation
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            return jsonify({'success': False, 'message': 'Please enter a valid email address'})

        # Department validation
        allowed_depts = ('Computer Science', 'Mechanical', 'Civil', 'Electrical', 'Electronics', 'IT', 'MBA', 'MCA', 'Faculty', 'Staff')
        if department not in allowed_depts:
            return jsonify({'success': False, 'message': 'Please select a valid department'})

        # Vehicle number validation
        vehicle_regex = r'^[A-Z]{2}[-\s]?\d{2}[-\s]?[A-Z]{1,2}[-\s]?\d{4}$'
        if not re.match(vehicle_regex, vehicle_no):
            return jsonify({'success': False, 'message': 'Invalid vehicle number. Format: MH-24-XX-0000'})

        # Vehicle type validation
        if vehicle_type not in ('two_wheeler', 'four_wheeler'):
            return jsonify({'success': False, 'message': 'Invalid vehicle type'})

        # Phone number validation (10 digits, starts with 6-9)
        phone_regex = r'^[6-9]\d{9}$'
        if not re.match(phone_regex, phone):
            return jsonify({'success': False, 'message': 'Phone number must be a valid 10-digit number starting with 6-9'})

        # Password validation
        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'})

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        existing = cur.fetchone()
        if existing:
            cur.close()
            return jsonify({'success': False, 'message': 'Email already registered'})

        cur.execute("""
            INSERT INTO users (full_name, email, password, vehicle_no, phone, department, vehicle_type, role)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (full_name, email, hash_password(password), vehicle_no, phone, department, vehicle_type, role))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True, 'message': 'Account created successfully'})

    return render_template('login.html', show_signup=True)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html',
                           user_name=session.get('user_name'),
                           user_email=session.get('user_email'))


# ─── API: Parking Slots ───────────────────────────────────────────────────────

@app.route('/api/slots')
@login_required
def get_slots():
    cur = mysql.connection.cursor()
    update_slot_statuses(cur)
    
    now = datetime.now()
    current_date = now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M')
    
    # Fetch active bookings for today to calculate available periods and partially booked status
    cur.execute("""
        SELECT slot_id, time_slot, end_time_slot 
        FROM bookings 
        WHERE booking_date = %s AND status = 'active'
    """, (current_date,))
    today_bookings = cur.fetchall()
    
    bookings_by_slot = {}
    for b in today_bookings:
        sid = b['slot_id']
        if sid not in bookings_by_slot:
            bookings_by_slot[sid] = []
        bookings_by_slot[sid].append(b)
        
    cur.execute("""
        SELECT ps.*, 
               b.id as booking_id,
               u.full_name as booked_by_name, 
               u.vehicle_no as booked_vehicle
        FROM parking_slots ps
        LEFT JOIN bookings b ON ps.id = b.slot_id 
                            AND b.status = 'active'
                            AND b.booking_date = %s
                            AND %s >= b.time_slot
                            AND %s < b.end_time_slot
        LEFT JOIN users u ON b.user_id = u.id
        ORDER BY ps.zone, ps.slot_number
    """, (current_date, current_time, current_time))
    slots = cur.fetchall()
    cur.close()

    # Group by zone
    zones = {}
    for slot in slots:
        zone = slot['zone']
        if zone not in zones:
            zones[zone] = []
            
        display_status = slot['status']
        sid = slot['id']
        slot_bookings = bookings_by_slot.get(sid, [])
        
        if display_status == 'available' and slot_bookings:
            # Sort bookings by start time
            slot_bookings.sort(key=lambda x: x['time_slot'])
            
            # Check available minutes
            start_min = 480
            end_limit_min = 1140
            
            # Adjust if today and current time has passed
            current_mins = now.hour * 60 + now.minute
            if current_mins > start_min:
                start_min = current_mins
                
            available_mins = 0
            for b in slot_bookings:
                b_start = time_to_minutes(b['time_slot'])
                b_end = time_to_minutes(b['end_time_slot'])
                
                if b_start > start_min:
                    available_mins += (b_start - start_min)
                if b_end > start_min:
                    start_min = b_end
                    
            if start_min < end_limit_min:
                available_mins += (end_limit_min - start_min)
                
            if available_mins < 30:
                display_status = 'occupied'  # Fully Booked
            else:
                display_status = 'partially_booked'
                
        booked_intervals = [f"{b['time_slot']} - {b['end_time_slot']}" for b in slot_bookings]
        
        zones[zone].append({
            'id': slot['id'],
            'slot_number': slot['slot_number'],
            'zone': zone,
            'slot_type': slot['slot_type'],
            'status': display_status,
            'booked_by': slot['booked_by_name'],
            'booked_vehicle': slot['booked_vehicle'],
            'booked_intervals': booked_intervals
        })
    return jsonify({'success': True, 'zones': zones})


# Zone A & B: two_wheeler only, Zone C: four_wheeler only, Zone D: faculty/admin any vehicle
VEHICLE_SLOT_MAP = {
    'two_wheeler': ('two_wheeler',),
    'four_wheeler': ('four_wheeler',),
}


@app.route('/api/book', methods=['POST'])
@login_required
def book_slot():
    data = request.get_json()
    slot_id = data.get('slot_id')
    time_slot = data.get('time_slot', '').strip()
    booking_date = data.get('booking_date', '').strip()
    duration = int(data.get('duration', 120))  # duration in minutes
    user_id = session['user_id']
    user_vehicle_type = session.get('vehicle_type', 'two_wheeler')
    user_role = session.get('role', 'student')

    if not time_slot or not booking_date:
        return jsonify({'success': False, 'message': 'Please select a date and time slot'})
    try:
        slot_hour = int(time_slot.split(':')[0])
        slot_min  = int(time_slot.split(':')[1])
        bdate = datetime.strptime(booking_date, '%Y-%m-%d').date()
    except (ValueError, IndexError):
        return jsonify({'success': False, 'message': 'Invalid date or time format'})

    if not (8 <= slot_hour < 19):
        return jsonify({'success': False, 'message': 'Start time must be between 8:00 AM and 7:00 PM'})
    if duration < 15 or duration > 240:
        return jsonify({'success': False, 'message': 'Duration must be between 15 minutes and 4 hours (240 minutes)'})
    
    # Calculate end time based on start hour, slot_min, and duration in minutes
    start_mins = slot_hour * 60 + slot_min
    end_mins = start_mins + duration
    
    if end_mins > 19 * 60: # exceeds 7:00 PM (1140 minutes)
        end_h = end_mins // 60
        end_m = end_mins % 60
        return jsonify({'success': False, 'message': f'End time {str(end_h).zfill(2)}:{str(end_m).zfill(2)} exceeds 7:00 PM limit'})
        
    end_hour = end_mins // 60
    end_minute = end_mins % 60
    end_time_str = f"{str(end_hour).zfill(2)}:{str(end_minute).zfill(2)}"

    if bdate < date.today():
        return jsonify({'success': False, 'message': 'Cannot book for a past date'})

    cur = mysql.connection.cursor()
    update_slot_statuses(cur)

    # Check if user already has an active booking that overlaps with this time period
    cur.execute("""
        SELECT b.*, ps.slot_number 
        FROM bookings b
        JOIN parking_slots ps ON b.slot_id = ps.id
        WHERE b.user_id = %s 
          AND b.status = 'active'
          AND b.booking_date = %s
          AND b.time_slot < %s
          AND b.end_time_slot > %s
    """, (user_id, booking_date, end_time_str, time_slot))
    user_overlap = cur.fetchone()
    if user_overlap:
        cur.close()
        return jsonify({
            'success': False, 
            'message': 'Already booked'
        })

    # Check slot
    cur.execute("SELECT * FROM parking_slots WHERE id = %s", (slot_id,))
    slot = cur.fetchone()
    if not slot:
        cur.close()
        return jsonify({'success': False, 'message': 'Slot not found'})
    if slot['status'] in ('maintenance', 'reserved'):
        cur.close()
        return jsonify({'success': False, 'message': f"Slot is not available: it is under {slot['status']}"})

    # ── Vehicle type enforcement ─────────────────────────────────────────────
    if user_role in ('admin', 'faculty'):
        pass  # faculty and admin can park anywhere
    else:
        allowed_types = VEHICLE_SLOT_MAP.get(user_vehicle_type, ('two_wheeler',))
        if slot['slot_type'] not in allowed_types:
            cur.close()
            type_labels = {'two_wheeler': 'Two Wheeler (Zone A/B)',
                           'four_wheeler': 'Four Wheeler (Zone C)',
                           'faculty': 'Faculty (Zone D)',
                           'handicapped': 'Handicapped (Zone D)'}
            allowed_label = ', '.join(type_labels.get(t, t) for t in allowed_types)
            return jsonify({'success': False,
                            'message': f'Your vehicle can only park in: {allowed_label} slots'})

    # Check if this slot already has an active booking that overlaps with this time period
    cur.execute("""
        SELECT * FROM bookings
        WHERE slot_id = %s
          AND status = 'active'
          AND booking_date = %s
          AND time_slot < %s
          AND end_time_slot > %s
    """, (slot_id, booking_date, end_time_str, time_slot))
    slot_overlap = cur.fetchone()
    if slot_overlap:
        cur.close()
        return jsonify({'success': False, 'message': 'This slot is already booked'})

    # Generate booking token
    token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    # Create booking
    cur.execute("""
        INSERT INTO bookings (user_id, slot_id, booking_token, status, booking_date, time_slot, end_time_slot, duration)
        VALUES (%s, %s, %s, 'active', %s, %s, %s, %s)
    """, (user_id, slot_id, token, booking_date, time_slot, end_time_str, duration))

    # Update slot statuses right away to sync real-time status in DB
    update_slot_statuses(cur)
    mysql.connection.commit()
    # Fetch user phone number for the SMS popup
    cur.execute("SELECT phone FROM users WHERE id = %s", (user_id,))
    user_data = cur.fetchone()
    phone_num = user_data['phone'] if user_data else 'your mobile'
    cur.close()

    response_data = {
        'success': True,
        'message': 'Slot booked successfully',
        'token': token,
        'slot_number': slot['slot_number'],
        'zone': slot['zone'],
        'time_slot': time_slot,
        'end_time': end_time_str,
        'duration': duration,
        'booking_date': booking_date,
        'phone': phone_num
    }

    # Trigger background alert (Bank SMS style)
    threading.Thread(target=send_automatic_alert, args=(response_data,)).start()

    return jsonify(response_data)


@app.route('/api/cancel', methods=['POST'])
@login_required
def cancel_booking():
    user_id = session['user_id']
    data = request.get_json() or {}
    booking_id = data.get('booking_id')
    
    cur = mysql.connection.cursor()
    update_slot_statuses(cur)

    if booking_id:
        cur.execute("""
            SELECT b.*, ps.slot_number, ps.zone
            FROM bookings b
            JOIN parking_slots ps ON b.slot_id = ps.id
            WHERE b.id = %s AND b.user_id = %s AND b.status = 'active'
        """, (booking_id, user_id))
    else:
        cur.execute("""
            SELECT b.*, ps.slot_number, ps.zone
            FROM bookings b
            JOIN parking_slots ps ON b.slot_id = ps.id
            WHERE b.user_id = %s AND b.status = 'active'
            ORDER BY b.booking_date ASC, b.time_slot ASC
        """, (user_id,))
    booking = cur.fetchone()

    if not booking:
        cur.close()
        return jsonify({'success': False, 'message': 'No active booking found'})

    cur.execute("UPDATE bookings SET status = 'cancelled', end_time = NOW() WHERE id = %s", (booking['id'],))
    update_slot_statuses(cur)
    mysql.connection.commit()
    cur.close()

    return jsonify({'success': True, 'message': f'Booking for slot {booking["slot_number"]} cancelled'})


@app.route('/api/check_in', methods=['POST'])
@login_required
def check_in():
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    update_slot_statuses(cur)
    
    now = datetime.now()
    current_date = now.strftime('%Y-%m-%d')
    
    cur.execute("""
        SELECT b.*, ps.slot_number 
        FROM bookings b
        JOIN parking_slots ps ON b.slot_id = ps.id
        WHERE b.user_id = %s AND b.status = 'active' AND b.booking_date = %s
    """, (user_id, current_date))
    booking = cur.fetchone()
    
    if not booking:
        cur.close()
        return jsonify({'success': False, 'message': 'No active booking found for today'})
        
    if booking['checked_in']:
        cur.close()
        return jsonify({'success': True, 'message': 'Already checked in!'})
        
    start_min = time_to_minutes(booking['time_slot'])
    current_mins = now.hour * 60 + now.minute
    
    if current_mins < start_min - 15:
        cur.close()
        return jsonify({'success': False, 'message': f"Too early! Check-in starts 15 mins before ({booking['time_slot']})"})
        
    if current_mins >= start_min + 15:
        cur.execute("UPDATE bookings SET status = 'cancelled', end_time = NOW() WHERE id = %s", (booking['id'],))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': False, 'message': 'Too late! Your booking was auto-released due to no check-in.'})
        
    cur.execute("UPDATE bookings SET checked_in = 1 WHERE id = %s", (booking['id'],))
    mysql.connection.commit()
    cur.close()
    
    return jsonify({'success': True, 'message': f"Checked in successfully for slot {booking['slot_number']}!"})


@app.route('/api/my_booking')
@login_required
def my_booking():
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    update_slot_statuses(cur)

    cur.execute("""
        SELECT b.*, ps.slot_number, ps.zone, ps.slot_type
        FROM bookings b
        JOIN parking_slots ps ON b.slot_id = ps.id
        WHERE b.user_id = %s AND b.status = 'active'
        ORDER BY b.booking_date ASC, b.time_slot ASC
    """, (user_id,))
    active_bookings = cur.fetchall()

    now = datetime.now()
    current_date = now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M')

    active_now = None
    for b in active_bookings:
        if hasattr(b['booking_date'], 'strftime'):
            bdate_str = b['booking_date'].strftime('%Y-%m-%d')
        else:
            bdate_str = str(b['booking_date'])
        b['booking_date'] = bdate_str
        if b['duration'] is not None:
            b['duration'] = int(b['duration'])
        b['checked_in'] = int(b['checked_in']) if b['checked_in'] is not None else 0
        
        # Calculate grace remaining only if within the check-in window (starting 15m before start)
        if not b['checked_in'] and bdate_str == current_date:
            b_start = time_to_minutes(b['time_slot'])
            current_mins = now.hour * 60 + now.minute
            if current_mins >= b_start - 15:
                grace_limit = b_start + 15
                b['grace_remaining'] = max(0, grace_limit - current_mins)
            else:
                b['grace_remaining'] = None
        else:
            b['grace_remaining'] = None

        if bdate_str == current_date and b['time_slot'] <= current_time < b['end_time_slot']:
            active_now = b

    booking = active_now if active_now else (active_bookings[0] if active_bookings else None)

    for b in active_bookings:
        if hasattr(b['booking_date'], 'strftime'):
            b['booking_date'] = b['booking_date'].strftime('%Y-%m-%d')
        if b['duration'] is not None:
            b['duration'] = int(b['duration'])
        b['checked_in'] = int(b['checked_in']) if b['checked_in'] is not None else 0

    cur.execute("""
        SELECT b.*, ps.slot_number, ps.zone
        FROM bookings b
        JOIN parking_slots ps ON b.slot_id = ps.id
        WHERE b.user_id = %s
        ORDER BY b.booking_date DESC, b.time_slot DESC LIMIT 5
    """, (user_id,))
    history = cur.fetchall()
    cur.close()

    for h in history:
        if hasattr(h['booking_date'], 'strftime'):
            h['booking_date'] = h['booking_date'].strftime('%Y-%m-%d')
        if h['duration'] is not None:
            h['duration'] = int(h['duration'])
        h['checked_in'] = int(h['checked_in']) if h['checked_in'] is not None else 0

    return jsonify({
        'success': True,
        'active_booking': booking,
        'history': history
    })


@app.route('/api/stats')
@login_required
def get_stats():
    cur = mysql.connection.cursor()
    update_slot_statuses(cur)
    
    cur.execute("SELECT COUNT(*) as total FROM parking_slots")
    total = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) as occupied FROM parking_slots WHERE status = 'occupied'")
    occupied = cur.fetchone()['occupied']
    cur.execute("SELECT COUNT(*) as available FROM parking_slots WHERE status = 'available'")
    available = cur.fetchone()['available']
    cur.close()
    
    return jsonify({
        'success': True,
        'total': total,
        'occupied': occupied,
        'available': available
    })


@app.route('/api/slot_availability')
@login_required
def get_slot_availability():
    slot_id = request.args.get('slot_id')
    booking_date = request.args.get('booking_date', '').strip()
    
    if not slot_id or not booking_date:
        return jsonify({'success': False, 'message': 'Missing slot_id or booking_date'})
        
    try:
        bdate = datetime.strptime(booking_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format'})

    cur = mysql.connection.cursor()
    update_slot_statuses(cur)
    
    # Fetch active bookings for this slot on this date
    cur.execute("""
        SELECT time_slot, end_time_slot 
        FROM bookings 
        WHERE slot_id = %s AND booking_date = %s AND status = 'active'
        ORDER BY time_slot
    """, (slot_id, booking_date))
    booked_slots = cur.fetchall()
    cur.close()

    # Calculate remaining available periods
    # Booking window is 08:00 (480 mins) to 19:00 (1140 mins)
    start_min = 480
    end_limit_min = 1140
    
    now = datetime.now()
    if bdate == now.date():
        current_mins = now.hour * 60 + now.minute
        if current_mins > start_min:
            start_min = current_mins
            
    available_intervals = []
    
    for b in booked_slots:
        b_start = time_to_minutes(b['time_slot'])
        b_end = time_to_minutes(b['end_time_slot'])
        
        if b_start > start_min:
            available_intervals.append((start_min, b_start))
        
        if b_end > start_min:
            start_min = b_end
            
    if start_min < end_limit_min:
        available_intervals.append((start_min, end_limit_min))
        
    # Format intervals nicely
    formatted_intervals = []
    for s, e in available_intervals:
        if (e - s) >= 30:
            formatted_intervals.append({
                'start_str': minutes_to_time(s),
                'end_str': minutes_to_time(e),
                'display': f"{format_time_12hr(s)} - {format_time_12hr(e)}"
            })
        
    return jsonify({
        'success': True,
        'available_periods': formatted_intervals
    })


# ─── Profile ──────────────────────────────────────────────────────────────────

@app.route('/api/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session['user_id']
    if request.method == 'GET':
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, full_name, email, vehicle_no, vehicle_type, phone, department, created_at FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        cur.close()
        return jsonify({'success': True, 'user': user})

    data = request.get_json()
    vehicle_type = data.get('vehicle_type', 'two_wheeler')
    if vehicle_type not in ('two_wheeler', 'four_wheeler'):
        vehicle_type = 'two_wheeler'
    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE users SET full_name=%s, vehicle_no=%s, phone=%s, department=%s, vehicle_type=%s
        WHERE id = %s
    """, (data['full_name'], data['vehicle_no'].upper(), data['phone'], data['department'], vehicle_type, user_id))
    mysql.connection.commit()
    session['user_name'] = data['full_name']
    session['vehicle_no'] = data['vehicle_no'].upper()
    session['vehicle_type'] = vehicle_type
    cur.close()
    return jsonify({'success': True, 'message': 'Profile updated!'})


@app.route('/api/admin/users')
@login_required
def admin_get_users():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, full_name, email, vehicle_no, vehicle_type, phone, department, role, created_at FROM users")
    users = cur.fetchall()
    cur.close()
    
    # Format dates
    for u in users:
        if u['created_at'] and hasattr(u['created_at'], 'strftime'):
            u['created_at'] = u['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            
    return jsonify({'success': True, 'users': users})


@app.route('/api/admin/bookings')
@login_required
def admin_get_bookings():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT b.id, b.booking_token, b.status, b.booking_date, b.time_slot, b.end_time_slot, b.duration, b.start_time, b.checked_in,
               u.full_name as user_name, u.email as user_email,
               ps.slot_number, ps.zone
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN parking_slots ps ON b.slot_id = ps.id
        ORDER BY b.booking_date DESC, b.time_slot DESC
    """)
    bookings = cur.fetchall()
    cur.close()
    
    for b in bookings:
        if b['booking_date'] and hasattr(b['booking_date'], 'strftime'):
            b['booking_date'] = b['booking_date'].strftime('%Y-%m-%d')
        if b['start_time'] and hasattr(b['start_time'], 'strftime'):
            b['start_time'] = b['start_time'].strftime('%Y-%m-%d %H:%M:%S')
        if b['duration'] is not None:
            b['duration'] = int(b['duration'])
        b['checked_in'] = int(b['checked_in']) if b['checked_in'] is not None else 0
            
    return jsonify({'success': True, 'bookings': bookings})


@app.route('/api/admin/users/update', methods=['POST'])
@login_required
def admin_update_user():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
        
    data = request.get_json() or {}
    user_id = data.get('id')
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip()
    vehicle_no = data.get('vehicle_no', '').strip().upper()
    vehicle_type = data.get('vehicle_type', 'two_wheeler').strip()
    phone = data.get('phone', '').strip()
    department = data.get('department', '').strip()
    role = data.get('role', 'student').strip()
    
    if not user_id or not full_name or not email:
        return jsonify({'success': False, 'message': 'Missing required fields (Name or Email)'})
        
    if vehicle_type not in ('two_wheeler', 'four_wheeler'):
        return jsonify({'success': False, 'message': 'Invalid vehicle type'})
        
    if role not in ('student', 'faculty', 'admin'):
        return jsonify({'success': False, 'message': 'Invalid role'})
        
    cur = mysql.connection.cursor()
    
    # Check if email is already taken by another user
    cur.execute("SELECT id FROM users WHERE email = %s AND id != %s", (email, user_id))
    existing = cur.fetchone()
    if existing:
        cur.close()
        return jsonify({'success': False, 'message': 'Email is already in use by another user'})
        
    # Update the user
    cur.execute("""
        UPDATE users 
        SET full_name = %s, email = %s, vehicle_no = %s, vehicle_type = %s, phone = %s, department = %s, role = %s
        WHERE id = %s
    """, (full_name, email, vehicle_no, vehicle_type, phone, department, role, user_id))
    mysql.connection.commit()
    cur.close()
    
    # Sync session if the logged in admin edited their own record
    if int(user_id) == session.get('user_id'):
        session['user_name'] = full_name
        session['user_email'] = email
        session['vehicle_no'] = vehicle_no
        session['vehicle_type'] = vehicle_type
        session['role'] = role
        
    return jsonify({'success': True, 'message': 'User details updated successfully'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)
