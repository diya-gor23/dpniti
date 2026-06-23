// Signup Page Script
<script src="config.js"></script>

const signupForm = document.getElementById('signupForm');
const nameInput = document.getElementById('signupName');
const emailInput = document.getElementById('signupEmail');
const passwordInput = document.getElementById('signupPassword');
const confirmPasswordInput = document.getElementById('confirmPassword');

const nameError = document.getElementById('nameError');
const emailError = document.getElementById('emailError');
const passwordError = document.getElementById('passwordError');
const confirmError = document.getElementById('confirmError');
const signupError = document.getElementById('signupError');
const successMessage = document.getElementById('successMessage');

// Email validation regex
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Clear error on input
nameInput.addEventListener('input', () => {
    nameError.textContent = '';
});

emailInput.addEventListener('input', () => {
    emailError.textContent = '';
});

passwordInput.addEventListener('input', () => {
    passwordError.textContent = '';
    confirmError.textContent = '';
});

confirmPasswordInput.addEventListener('input', () => {
    confirmError.textContent = '';
});

// Form submission
signupForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // Clear previous messages
    signupError.textContent = '';
    successMessage.textContent = '';
    successMessage.classList.remove('show');

    // Validation
    let isValid = true;

    if (!nameInput.value.trim()) {
        nameError.textContent = 'Name is required';
        isValid = false;
    } else if (nameInput.value.trim().length < 2) {
        nameError.textContent = 'Name must be at least 2 characters';
        isValid = false;
    } else if (nameInput.value.trim().length > 50) {
        nameError.textContent = 'Name must not exceed 50 characters';
        isValid = false;
    }

    if (!emailInput.value.trim()) {
        emailError.textContent = 'Email is required';
        isValid = false;
    } else if (!emailRegex.test(emailInput.value)) {
        emailError.textContent = 'Please enter a valid email';
        isValid = false;
    }

    if (!passwordInput.value) {
        passwordError.textContent = 'Password is required';
        isValid = false;
    } else if (passwordInput.value.length < 6) {
        passwordError.textContent = 'Password must be at least 6 characters';
        isValid = false;
    } else if (passwordInput.value.length > 128) {
        passwordError.textContent = 'Password is too long';
        isValid = false;
    }

    if (!confirmPasswordInput.value) {
        confirmError.textContent = 'Please confirm your password';
        isValid = false;
    } else if (passwordInput.value !== confirmPasswordInput.value) {
        confirmError.textContent = 'Passwords do not match';
        isValid = false;
    }

    if (!isValid) {
        return;
    }

    // Prepare data
    const signupData = {
        name: nameInput.value.trim(),
        email: emailInput.value.trim(),
        password: passwordInput.value
    };

    try {
        // Disable button during submission
        const submitBtn = signupForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Creating Account...';

        // Send signup request to backend
        const response = await fetch(`${CONFIG.BACKEND_URL}/api/auth/signup`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(signupData)
        });

        const data = await response.json();

        if (response.ok) {
            // Success
            successMessage.textContent = '✓ ' + data.message;
            successMessage.classList.add('show');
            
            // Clear form
            signupForm.reset();
            
            // Redirect to login page after 2 seconds
            setTimeout(() => {
                alert('Account created successfully! Please login.');
                window.location.href = 'index.html';
            }, 2000);
        } else {
            // Error from server
            signupError.textContent = data.message || 'Signup failed. Please try again.';
        }

        // Re-enable button
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sign Up';

    } catch (error) {
        console.error('Error:', error);
        signupError.textContent = 'Connection error. Make sure the backend is running on ' + CONFIG.API_URL;
        
        // Re-enable button
        const submitBtn = signupForm.querySelector('button[type="submit"]');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sign Up';
    }
});
