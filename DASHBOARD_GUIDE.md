# 📊 Dashboard Guide

## Overview
The dashboard appears after successful login and displays:
- Sticky navbar with navigation
- Welcome hero section
- 4 auto-sliding image galleries (Academic Calendar, Holidays, Exam Timetable, Class Timetable)
- Faculty and Students sections
- Footer

## Features Implemented

### ✅ Sticky Navbar
- Fixed position on scroll
- Logo on left
- About Us, Contact Us, Profile buttons on right
- Mobile responsive with hamburger menu
- Smooth scroll to sections

### ✅ Hero Section
- Full-screen welcome message: "Welcome to 2023 Batch"
- Animated gradient background
- Floating circle decorations

### ✅ Auto-Sliding Image Galleries (4 Tabs)
Each tab auto-plays images every **2 seconds**:

1. **Academic Calendar** - 3 images
2. **Holidays Calendar** - 4 images (Jan-Dec quarterly)
3. **Exam Timetable** - 3 images (IA, Mid, End Semester)
4. **Class Timetable** - 7 images (Division 1-7)

Features:
- Auto-advance every 2 seconds
- Pause on hover
- Navigation dots
- Click dots to jump to specific slide
- Smooth fade transitions

### ✅ Faculty & Students Section
Two large interactive cards:
- Faculty card - View faculty profiles
- Students card - View student directory
- Hover animations
- Gradient backgrounds

### ✅ Footer
- Copyright information
- Quick links (Privacy, Terms, Contact)
- Responsive layout

---

## 🎨 Customization Guide

### Replace Placeholder Images

Currently using placeholder images from `via.placeholder.com`. Replace them with your actual images:

#### **Option 1: Use Local Images**

1. Create an `images` folder in the frontend directory:
   ```
   frontend/
   ├── images/
   │   ├── academic/
   │   ├── holidays/
   │   ├── exams/
   │   └── timetable/
   ```

2. Add your images to respective folders

3. Update `dashboard.html` image src:
   ```html
   <!-- Before -->
   <img src="https://via.placeholder.com/400x300/667eea/ffffff?text=Academic+Calendar+2023" alt="Calendar 1">
   
   <!-- After -->
   <img src="images/academic/calendar-2023.jpg" alt="Calendar 1">
   ```

#### **Option 2: Use External URLs**

Replace placeholder URLs with your image URLs:
```html
<img src="https://your-domain.com/images/calendar.jpg" alt="Calendar 1">
```

### Change Auto-Play Speed

In `dashboard.js`, update the interval (in milliseconds):
```javascript
const sliders = [
    { id: 'slider1', dotsId: 'dots1', interval: 3000 }, // 3 seconds
    { id: 'slider2', dotsId: 'dots2', interval: 2500 }, // 2.5 seconds
    // ...
];
```

### Modify Colors

In `dashboard.css`, change the CSS variables:
```css
:root {
    --primary-color: #667eea;    /* Change primary color */
    --secondary-color: #764ba2;  /* Change secondary color */
    --accent-color: #f093fb;     /* Change accent color */
}
```

### Update Logo

Replace the logo image URL in `dashboard.html`:
```html
<div class="nav-logo">
    <img src="path/to/your/logo.png" alt="Logo">
    <span class="logo-text">Your School Name</span>
</div>
```

---

## 📱 Responsive Design

The dashboard is fully responsive with breakpoints:
- **Desktop**: > 768px (2-column grid)
- **Tablet**: 481px - 768px (1-column grid)
- **Mobile**: ≤ 480px (simplified layout)

---

## 🔧 Image Slider Usage

### Add More Slides

To add more slides to any slider:

1. Add new slide in HTML:
```html
<div class="slide">
    <img src="path/to/image.jpg" alt="Description">
    <div class="slide-caption">Caption Text</div>
</div>
```

2. The JavaScript will automatically:
   - Create navigation dots
   - Include in auto-play rotation
   - Handle transitions

### Remove Slides

Simply delete the `<div class="slide">...</div>` block. The slider adapts automatically.

---

## 🎯 Additional Features

### Profile Menu
Clicking "Profile" shows a dropdown with:
- User name and email (from localStorage)
- Logout button

### Logout Functionality
Clears authentication data and redirects to login page.

### Smooth Scrolling
All anchor links scroll smoothly to their target sections.

### Scroll Animations
Cards fade in and slide up when scrolling into view.

---

## 📂 File Structure

```
frontend/
├── dashboard.html      # Main dashboard HTML
├── dashboard.css       # Dashboard styling
├── dashboard.js        # Slider logic, animations, interactions
├── index.html          # Login page
├── signup.html         # Signup page
├── script.js           # Login logic (updated to redirect to dashboard)
└── signup.js           # Signup logic
```

---

## 🚀 How to Use

### As a Student/User:
1. Login through the login page
2. Automatically redirected to dashboard
3. View all academic resources in one place
4. Navigate using navbar
5. Click Profile to logout

### As an Admin:
1. Replace placeholder images with actual content
2. Update colors and branding
3. Modify slider speed if needed
4. Add/remove slides as required

---

## 🔐 Authentication Flow

1. User logs in via `index.html`
2. Backend validates credentials
3. On success:
   - Token saved to localStorage
   - User info saved (name, email)
   - Redirect to `dashboard.html`
4. Dashboard checks for token on load
5. Profile menu shows user info
6. Logout clears data and redirects to login

---

## 💡 Tips

1. **Image Optimization**: 
   - Use optimized images (JPG for photos, PNG for graphics)
   - Recommended size: 400x300px for sliders
   - Compress images to reduce load time

2. **Content Organization**:
   - Keep images organized in folders
   - Use descriptive file names
   - Maintain consistent aspect ratios

3. **Performance**:
   - Lazy load images if you have many
   - Use CDN for faster loading
   - Minify CSS/JS for production

4. **Accessibility**:
   - Add descriptive alt text to images
   - Ensure sufficient color contrast
   - Test with keyboard navigation

---

## 🐛 Troubleshooting

**Images not loading?**
- Check file paths are correct
- Ensure images exist in specified location
- Check browser console for errors

**Slider not auto-playing?**
- Check JavaScript console for errors
- Verify slider IDs match in HTML and JS
- Ensure slides have class "slide"

**Mobile menu not working?**
- Check hamburger icon is visible
- Verify JavaScript is loaded
- Test in browser dev tools mobile view

---

## 🎨 Example Image Replacement

```html
<!-- Academic Calendar Slider -->
<div class="slider" id="slider1">
    <div class="slide active">
        <img src="images/academic/sem1-calendar.jpg" alt="Semester 1">
        <div class="slide-caption">Semester 1 Schedule</div>
    </div>
    <div class="slide">
        <img src="images/academic/sem2-calendar.jpg" alt="Semester 2">
        <div class="slide-caption">Semester 2 Schedule</div>
    </div>
    <div class="slide">
        <img src="images/academic/academic-year.jpg" alt="Full Year">
        <div class="slide-caption">Full Academic Year</div>
    </div>
</div>
```

---

## 📞 Support

For issues or customization help, refer to:
- Main README.md
- SETUP_GUIDE.txt
- Browser developer console for errors

---

**Enjoy your new dashboard! 🎉**
