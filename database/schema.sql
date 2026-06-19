-- ============================================
-- DATABASE SETUP
-- ============================================

-- Create Database
CREATE DATABASE IF NOT EXISTS auth_db;

-- Use the database
USE auth_db;

-- ============================================
-- CREATE USERS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- TABLE DETAILS
-- ============================================
-- id:        Auto-incremented primary key (unique identifier for each user)
-- name:      User's full name (max 50 characters)
-- email:     User's email (max 100 characters, must be unique)
-- password:  Hashed password (max 255 characters to store bcrypt hash)
-- created_at: Timestamp of account creation (automatically set to current time)

-- ============================================
-- OPTIONAL: Insert Sample Data (for testing)
-- ============================================
-- Remove the leading dashes to run these sample inserts

-- INSERT INTO users (name, email, password) VALUES 
-- ('John Doe', 'john@example.com', '$2a$10$...'); -- Remember: passwords must be hashed

-- ============================================
-- OPTIONAL: Drop Database (use if needed to reset)
-- ============================================
-- DROP DATABASE IF EXISTS auth_db;
