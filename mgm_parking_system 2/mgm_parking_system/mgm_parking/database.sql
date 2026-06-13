-- ============================================================
--  MGM College Nanded - Smart Parking System Database
--  Run this in phpMyAdmin (XAMPP) or MySQL CLI
-- ============================================================

CREATE DATABASE IF NOT EXISTS mgm_parking CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE mgm_parking;

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    full_name    VARCHAR(100) NOT NULL,
    email        VARCHAR(150) NOT NULL UNIQUE,
    password     VARCHAR(255) NOT NULL,
    vehicle_no   VARCHAR(20),
    vehicle_type ENUM('two_wheeler','four_wheeler') DEFAULT 'two_wheeler',
    phone        VARCHAR(15),
    department   VARCHAR(100),
    role         ENUM('student','faculty','admin') DEFAULT 'student',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Parking Slots Table
CREATE TABLE IF NOT EXISTS parking_slots (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    slot_number VARCHAR(10) NOT NULL UNIQUE,
    zone        ENUM('A','B','C','D') NOT NULL,
    slot_type   ENUM('two_wheeler','four_wheeler','faculty','handicapped') DEFAULT 'two_wheeler',
    status      ENUM('available','occupied','reserved','maintenance') DEFAULT 'available'
);

-- Bookings Table
CREATE TABLE IF NOT EXISTS bookings (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    slot_id       INT NOT NULL,
    booking_token VARCHAR(20),
    status        ENUM('active','completed','cancelled') DEFAULT 'active',
    booking_date  DATE NOT NULL,
    time_slot     VARCHAR(5) NOT NULL,   -- e.g. '09:00'
    end_time_slot VARCHAR(5) NULL,       -- e.g. '11:00'
    duration      INT DEFAULT 120,       -- minutes
    checked_in    TINYINT DEFAULT 0,     -- 0=no, 1=yes
    start_time    DATETIME DEFAULT CURRENT_TIMESTAMP,
    end_time      DATETIME NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (slot_id) REFERENCES parking_slots(id)
);

-- ─── Seed Parking Slots ──────────────────────────────────────────────────────
-- NOTE: If upgrading an existing database, run these ALTER statements first:
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS vehicle_type ENUM('two_wheeler','four_wheeler') DEFAULT 'two_wheeler';
-- ALTER TABLE bookings ADD COLUMN IF NOT EXISTS booking_date DATE NOT NULL DEFAULT (CURDATE());
-- ALTER TABLE bookings ADD COLUMN IF NOT EXISTS time_slot VARCHAR(5) NOT NULL DEFAULT '08:00';

-- Zone A: Two Wheelers (20 slots)
INSERT INTO parking_slots (slot_number, zone, slot_type) VALUES
('A01','A','two_wheeler'),('A02','A','two_wheeler'),('A03','A','two_wheeler'),('A04','A','two_wheeler'),
('A05','A','two_wheeler'),('A06','A','two_wheeler'),('A07','A','two_wheeler'),('A08','A','two_wheeler'),
('A09','A','two_wheeler'),('A10','A','two_wheeler'),('A11','A','two_wheeler'),('A12','A','two_wheeler'),
('A13','A','two_wheeler'),('A14','A','two_wheeler'),('A15','A','two_wheeler'),('A16','A','two_wheeler'),
('A17','A','two_wheeler'),('A18','A','two_wheeler'),('A19','A','two_wheeler'),('A20','A','two_wheeler');

-- Zone B: Two Wheelers (20 slots)
INSERT INTO parking_slots (slot_number, zone, slot_type) VALUES
('B01','B','two_wheeler'),('B02','B','two_wheeler'),('B03','B','two_wheeler'),('B04','B','two_wheeler'),
('B05','B','two_wheeler'),('B06','B','two_wheeler'),('B07','B','two_wheeler'),('B08','B','two_wheeler'),
('B09','B','two_wheeler'),('B10','B','two_wheeler'),('B11','B','two_wheeler'),('B12','B','two_wheeler'),
('B13','B','two_wheeler'),('B14','B','two_wheeler'),('B15','B','two_wheeler'),('B16','B','two_wheeler'),
('B17','B','two_wheeler'),('B18','B','two_wheeler'),('B19','B','two_wheeler'),('B20','B','two_wheeler');

-- Zone C: Four Wheelers (15 slots)
INSERT INTO parking_slots (slot_number, zone, slot_type) VALUES
('C01','C','four_wheeler'),('C02','C','four_wheeler'),('C03','C','four_wheeler'),('C04','C','four_wheeler'),
('C05','C','four_wheeler'),('C06','C','four_wheeler'),('C07','C','four_wheeler'),('C08','C','four_wheeler'),
('C09','C','four_wheeler'),('C10','C','four_wheeler'),('C11','C','four_wheeler'),('C12','C','four_wheeler'),
('C13','C','four_wheeler'),('C14','C','four_wheeler'),('C15','C','four_wheeler');

-- Zone D: Faculty + Handicapped (10 slots)
INSERT INTO parking_slots (slot_number, zone, slot_type) VALUES
('D01','D','faculty'),('D02','D','faculty'),('D03','D','faculty'),('D04','D','faculty'),
('D05','D','faculty'),('D06','D','faculty'),('D07','D','faculty'),('D08','D','faculty'),
('D09','D','handicapped'),('D10','D','handicapped');

-- ─── Demo Admin User (password: admin123) ───────────────────────────────────
INSERT INTO users (full_name, email, password, vehicle_no, vehicle_type, phone, department, role)
VALUES ('Admin MGM', 'admin@mgmcollege.edu',
        SHA2('admin123', 256),
        'MH-24-AA-0001', 'four_wheeler', '9999999999', 'Administration', 'admin');
