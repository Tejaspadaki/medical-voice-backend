-- =========================================================
-- AuraDoc Clinical AI - Complete Relational SQL Schema
-- Database: SQLite / PostgreSQL compatible schema
-- =========================================================

-- Table: roles
CREATE TABLE roles (
	role_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	name VARCHAR(50) NOT NULL UNIQUE, 
	description VARCHAR(255), 
	permissions JSON
);

-- Table: users
CREATE TABLE users (
	user_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	email VARCHAR(255) NOT NULL UNIQUE, 
	hashed_password VARCHAR(255) NOT NULL, 
	full_name VARCHAR(100), 
	role_id INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL DEFAULT 1, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	FOREIGN KEY(role_id) REFERENCES roles (role_id) ON DELETE RESTRICT
);

-- Table: doctors
CREATE TABLE doctors (
	doctor_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	user_id INTEGER NOT NULL UNIQUE, 
	specialization VARCHAR(100) NOT NULL, 
	registration_no VARCHAR(50) NOT NULL UNIQUE, 
	department VARCHAR(100), 
	contact_phone VARCHAR(20), 
	created_at DATETIME NOT NULL, 
	FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

-- Table: patients
CREATE TABLE patients (
	patient_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	full_name VARCHAR(150) NOT NULL, 
	dob DATE, 
	gender VARCHAR(20) NOT NULL, 
	phone VARCHAR(20) NOT NULL, 
	email VARCHAR(255), 
	address TEXT, 
	emergency_contact VARCHAR(100), 
	blood_group VARCHAR(10), 
	preferred_language VARCHAR(30) DEFAULT 'Kannada', 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL
);

-- Table: consultations
CREATE TABLE consultations (
	consultation_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	patient_id INTEGER NOT NULL, 
	doctor_id INTEGER, 
	report_id VARCHAR(100) NOT NULL UNIQUE, 
	input_language VARCHAR(30) DEFAULT 'kn', 
	original_english_speech TEXT, 
	kannada_transcript TEXT NOT NULL, 
	symptoms JSON NOT NULL, 
	diagnosis JSON NOT NULL, 
	medications JSON NOT NULL, 
	advice JSON NOT NULL, 
	status VARCHAR(30) NOT NULL DEFAULT 'APPROVED', 
	signed_by_name VARCHAR(150), 
	signed_doctor_reg VARCHAR(50), 
	audio_filename VARCHAR(255), 
	pdf_filename VARCHAR(255), 
	pdf_file_path VARCHAR(500), 
	created_at DATETIME NOT NULL, 
	signed_at DATETIME NOT NULL, 
	FOREIGN KEY(patient_id) REFERENCES patients (patient_id) ON DELETE CASCADE, 
	FOREIGN KEY(doctor_id) REFERENCES users (user_id)
);

-- Table: medical_reports (PDF File Storage in SQL Database)
CREATE TABLE medical_reports (
	report_record_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	consultation_id INTEGER NOT NULL UNIQUE, 
	patient_id INTEGER NOT NULL, 
	doctor_id INTEGER, 
	report_code VARCHAR(100) NOT NULL UNIQUE, 
	pdf_filename VARCHAR(255) NOT NULL, 
	pdf_file_path VARCHAR(500) NOT NULL, 
	pdf_base64_data TEXT, 
	file_size_bytes INTEGER, 
	mime_type VARCHAR(50) NOT NULL DEFAULT 'application/pdf', 
	signed_doctor_name VARCHAR(150) NOT NULL, 
	signed_doctor_reg VARCHAR(50) NOT NULL, 
	status VARCHAR(30) NOT NULL DEFAULT 'CONFIRMED_SIGNED', 
	created_at DATETIME NOT NULL, 
	FOREIGN KEY(consultation_id) REFERENCES consultations (consultation_id) ON DELETE CASCADE, 
	FOREIGN KEY(patient_id) REFERENCES patients (patient_id) ON DELETE CASCADE, 
	FOREIGN KEY(doctor_id) REFERENCES users (user_id)
);
