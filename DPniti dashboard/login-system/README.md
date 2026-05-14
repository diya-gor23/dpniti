# 🔐 Complete Login & Signup System

A full-stack authentication system built with HTML, CSS, JavaScript (Frontend), Node.js + Express (Backend), and MySQL (Database).

## 📁 Project Structure

```
login-system/
├── frontend/
│   ├── index.html          # Login page
│   ├── signup.html         # Signup page
│   ├── style.css          # Shared styling
│   ├── script.js          # Login form logic
│   └── signup.js          # Signup form logic
│
├── backend/
│   ├── server.js          # Express server & API routes
│   ├── db.js              # MySQL connection pool
│   └── package.json       # Dependencies
│
└── database/
    └── schema.sql         # MySQL database schema
```

## ✨ Features

### Frontend
- ✅ Modern, responsive design
- ✅ Real-time form validation
- ✅ Client-side email validation
- ✅ Password confirmation validation
- ✅ Error messages for each field
- ✅ Success/failure feedback
- ✅ Mobile-friendly layout
- ✅ Smooth animations

### Backend
- ✅ Express.js REST API
- ✅ Secure password hashing with bcryptjs
- ✅ Email uniqueness validation
- ✅ CORS enabled for cross-origin requests
- ✅ Input validation
- ✅ Error handling
- ✅ Connection pooling

### Database
- ✅ MySQL with users table
- ✅ Unique email constraint
- ✅ Auto-increment ID
- ✅ Timestamp tracking

---

## 🚀 Getting Started

### Prerequisites
- **Node.js** (v14 or higher)
- **MySQL** (v5.7 or higher)
- A code editor (VS Code recommended)

### Step 1: Set Up MySQL Database

1. Open **MySQL Command Line Client** or **MySQL Workbench**

2. Run the SQL script from `database/schema.sql`:
   ```sql
   CREATE DATABASE IF NOT EXISTS auth_db;
   USE auth_db;
   
   CREATE TABLE IF NOT EXISTS users (
       id INT PRIMARY KEY AUTO_INCREMENT,
       name VARCHAR(50) NOT NULL,
       email VARCHAR(100) NOT NULL UNIQUE,
       password VARCHAR(255) NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

### Step 2: Configure Backend

1. Navigate to the backend folder:
   ```bash
   cd login-system/backend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. **IMPORTANT**: Update database credentials in `db.js`
   - Open `db.js`
   - Change `user` to your MySQL username (default: 'root')
   - Change `password` to your MySQL password
   - Example:
   ```javascript
   const pool = mysql.createPool({
       host: 'localhost',
       user: 'root',
       password: 'your_mysql_password', // ← Change this
       database: 'auth_db',
       // ...
   });
   ```

### Step 3: Run The Application

#### Start Backend Server
```bash
# From backend directory
npm start
```

You should see:
```
Server is running on http://localhost:5000
Make sure MySQL is running and database is set up
```

#### Open Frontend
1. Navigate to `frontend/index.html`
2. Open it in your web browser
3. Or run a local server:
   ```bash
   # From frontend directory (if you have Python installed)
   python -m http.server 8000
   
   # Then visit: http://localhost:8000
   ```

---

## 📝 API Endpoints

### POST /api/auth/signup
Register a new user

**Request:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "securepass123"
}
```

**Success Response (201):**
```json
{
  "success": true,
  "message": "Account created successfully! You can now login."
}
```

**Error Response (400):**
```json
{
  "success": false,
  "message": "Email already registered. Please login or use a different email"
}
```

### POST /api/auth/login
Authenticate a user

**Request:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "securepass123"
}
```

**Success Response (200):**
```json
{
  "success": true,
  "message": "Login successful!",
  "user": {
    "id": 1,
    "name": "John Doe",
    "email": "john@example.com"
  },
  "token": "auth_token_1"
}
```

**Error Response (401):**
```json
{
  "success": false,
  "message": "Invalid credentials"
}
```

### GET /api/health
Check server status

**Response (200):**
```json
{
  "success": true,
  "message": "Server is running"
}
```

---

## 🔒 Security Features

1. **Password Hashing**: Uses bcryptjs with salt rounds of 10
2. **Email Validation**: Both client-side and server-side validation
3. **Unique Emails**: Database constraint prevents duplicate registrations
4. **CORS**: Configured to accept requests from frontend
5. **Input Validation**: All fields validated before processing
6. **SQL Injection Prevention**: Uses parameterized queries

---

## 🧪 Testing the System

### Test Signup Flow
1. Go to signup page
2. Fill in details:
   - Name: "Test User"
   - Email: "test@example.com"
   - Password: "password123"
   - Confirm Password: "password123"
3. Click "Sign Up"
4. Should see success message and redirect to login

### Test Login Flow
1. Go to login page
2. Fill in details:
   - Name: "Test User"
   - Email: "test@example.com"
   - Password: "password123"
3. Click "Login"
4. Should see "Login successful!" message

### Test Validation
- Try signup with existing email → see error
- Try login with wrong password → see "Invalid credentials"
- Try signup with weak password → see validation error
- Try signup with mismatched passwords → see error

---

## 🛠️ Troubleshooting

### Error: "Connection error. Make sure the backend is running"
- Check if backend server is running on port 5000
- Run `npm start` in backend folder

### Error: "Cannot find module 'bcryptjs'"
- Run `npm install` in backend folder to install dependencies

### MySQL Connection Error
- Verify MySQL is running
- Check username and password in `backend/db.js`
- Ensure `auth_db` database exists

### CORS Error in Browser Console
- Make sure backend is running
- Check that frontend is calling `http://localhost:5000`

---

## 📦 Dependencies

### Backend
- **express**: Web framework
- **mysql2**: MySQL database driver
- **bcryptjs**: Password hashing
- **cors**: Cross-Origin Resource Sharing
- **dotenv**: Environment variables (optional)

Install with:
```bash
npm install
```

---

## 📄 Database Schema

```sql
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Column Details
- **id**: Unique identifier (auto-increment)
- **name**: User's full name (max 50 chars)
- **email**: User's email (max 100 chars, must be unique)
- **password**: Hashed password (max 255 chars for bcrypt)
- **created_at**: Account creation timestamp

---

## 🎨 Frontend Pages

### Login Page (index.html)
- Name field
- Email field
- Password field
- Login button
- Link to signup page
- Real-time validation

### Signup Page (signup.html)
- Name field
- Email field
- Password field
- Confirm password field
- Signup button
- Link to login page
- Password match validation

### Styling (style.css)
- Gradient background (purple/blue)
- Responsive layout
- Mobile optimizations
- Smooth animations
- Form validation styles

---

## 🔄 How It Works

### Signup Process
1. User fills signup form
2. Frontend validates input
3. JavaScript sends POST request to `/api/auth/signup`
4. Backend checks if email exists
5. Password is hashed with bcryptjs
6. User data saved to MySQL
7. Success message displayed

### Login Process
1. User fills login form
2. Frontend validates input
3. JavaScript sends POST request to `/api/auth/login`
4. Backend finds user by email
5. Password compared with hashed password
6. Name verified
7. Token returned on success
8. Error message on failure

---

## 🚀 Future Enhancements

- JWT token implementation
- Email verification
- Password reset functionality
- User dashboard
- Profile update feature
- Session management
- Rate limiting
- Two-factor authentication (2FA)

---

## 📞 Support

If you encounter any issues:
1. Check troubleshooting section above
2. Verify all files are in correct locations
3. Ensure dependencies are installed
4. Check MySQL is running
5. Look for error messages in browser console and terminal

---

## 📜 License

This project is open source and available for educational purposes.

---

Happy coding! 🎉
