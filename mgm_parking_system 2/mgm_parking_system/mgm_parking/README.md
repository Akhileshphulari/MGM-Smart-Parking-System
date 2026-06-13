# 🅿️ MGM Smart Parking System
### MGM College of Engineering & Technology, Nanded

---

## 📁 Project Structure

```
mgm_parking/
├── app.py              ← Flask backend (main server)
├── requirements.txt    ← Python dependencies
├── database.sql        ← MySQL database setup
├── templates/
│   ├── login.html      ← Login / Signup page
│   └── dashboard.html  ← Main app (parking map, profile, history)
└── README.md
```

---

## 🚀 Setup Instructions

### Step 1 — Start XAMPP
1. Open **XAMPP Control Panel**
2. Start **Apache** and **MySQL**

### Step 2 — Create Database
1. Open browser → go to `c`
2. Click **Import** tab
3. Choose file: `database.sql`
4. Click **Go** ✅

   OR run manually in phpMyAdmin SQL tab:
   ```sql
   source /path/to/database.sql
   ```

### Step 3 — Install Python Dependencies
Open terminal/cmd in the project folder:
```bash
pip install -r requirements.txt
```

> **Note**: On some systems you may need `mysqlclient` C library first:
> - Windows: `pip install mysqlclient` (may need Visual C++ build tools)
> - Ubuntu/Debian: `sudo apt-get install libmysqlclient-dev`
> - macOS: `brew install mysql-connector-c`

### Step 4 — Run Flask Server
```bash
python app.py
```
Server starts at: **http://localhost:5000**

---

## 🔑 Default Login (Admin)
| Field | Value |
|-------|-------|
| Email | admin@mgmcollege.edu |
| Password | admin123 |

---

## 🗺️ Parking Zones

| Zone | Type | Slots |
|------|------|-------|
| A | Two Wheelers | 20 |
| B | Two Wheelers | 20 |
| C | Four Wheelers | 15 |
| D | Faculty + Handicapped | 10 |
| **Total** | | **65** |

---

## ✨ Features
- ✅ Login / Signup with SHA-256 password hashing
- 🅿️ Live parking slot map (color-coded: green=free, red=occupied)
- 📍 Real-time slot booking with unique token
- 👤 User profile with vehicle number
- 📋 Booking history
- 🗺️ Campus layout overview
- ♿ Handicapped slot support
- 🎓 Faculty reserved zone
- 🔄 Auto-refresh every 30 seconds

---

## ⚙️ Configuration (app.py)
Change these if your MySQL setup differs:
```python
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'admin123'   # add password if set
app.config['MYSQL_DB'] = 'mgm_parking'
```
