# 📅 Academic Calendar Integration - Complete Setup

## ✅ What's Been Done:

### 1. **Folder Structure Created:**
```
frontend/
├── images/
│   └── academic/          ← Put calendar-page2.jpg here
├── documents/
│   └── acad_cal.pdf      ← Full PDF copied here
└── extract-pdf-page.html  ← Tool to extract PDF page
```

### 2. **Dashboard Updated:**
- Academic Calendar slider now looks for: `images/academic/calendar-page2.jpg`
- Click on the image opens the full PDF in a new tab
- Added "Click image to view full calendar" text
- Hover effect shows it's clickable (cursor changes, slight zoom)

### 3. **Files Modified:**
- ✅ dashboard.html - Updated Academic Calendar slider
- ✅ dashboard.js - Added `openCalendarPDF()` function
- ✅ dashboard.css - Added clickable slider styles
- ✅ acad_cal.pdf - Copied to documents folder

---

## 🚀 Quick Start (2 Methods):

### **METHOD 1: Use the PDF Extractor Tool (Easiest)**

1. **Open the extractor:**
   ```
   Double-click: frontend/extract-pdf-page.html
   ```

2. **Upload PDF:**
   - Click the upload area
   - Select `documents/acad_cal.pdf`
   - OR drag and drop the PDF

3. **Select page:**
   - Page number field shows "2" (already set)
   - Change if you want a different page

4. **Extract & Save:**
   - Click "Extract & Download Image"
   - Browser downloads "calendar-page2.jpg"
   - Move it to: `frontend/images/academic/calendar-page2.jpg`

5. **Refresh dashboard** and the image will appear!

---

### **METHOD 2: Screenshot (Quickest)**

1. **Open the PDF:**
   ```
   Double-click: frontend/documents/acad_cal.pdf
   ```

2. **Go to page 2**

3. **Take screenshot:**
   - Press: **Windows + Shift + S**
   - Select the calendar area
   - Screenshot saved to clipboard

4. **Save the image:**
   - Open Paint or any image editor
   - Paste (Ctrl + V)
   - Save as: `frontend/images/academic/calendar-page2.jpg`

5. **Done!** Refresh the dashboard

---

## 📌 How It Works:

### **Academic Calendar Slider:**
```html
<!-- In dashboard.html -->
<div class="slider clickable-slider" onclick="openCalendarPDF()">
    <div class="slide active">
        <img src="images/academic/calendar-page2.jpg" alt="Calendar">
        <div class="slide-caption">
            📅 Academic Calendar 2023-24 (Click to open full PDF)
        </div>
    </div>
</div>
```

### **JavaScript Function:**
```javascript
// In dashboard.js
function openCalendarPDF() {
    window.open('documents/acad_cal.pdf', '_blank');
}
```

### **Result:**
- ✅ Shows page 2 image in slider
- ✅ Auto-rotates with other slides every 2 seconds
- ✅ Click on image → Opens full PDF in new tab
- ✅ Hover effect shows it's clickable
- ✅ Fallback placeholder if image not found

---

## 🎨 Customization:

### **Change Which Page to Show:**
1. Extract different page using the tool
2. Save as `calendar-page2.jpg` in `images/academic/`

### **Add More Calendar Slides:**
Add to the slider in `dashboard.html`:
```html
<div class="slide">
    <img src="images/academic/calendar-page3.jpg" alt="Another page">
    <div class="slide-caption">Page 3 Caption</div>
</div>
```

### **Change PDF File:**
Replace `documents/acad_cal.pdf` with your new PDF

---

## 📂 File Locations:

| What | Where |
|------|-------|
| **Full PDF** | `frontend/documents/acad_cal.pdf` |
| **Page 2 Image** | `frontend/images/academic/calendar-page2.jpg` |
| **PDF Extractor Tool** | `frontend/extract-pdf-page.html` |
| **Dashboard** | `frontend/dashboard.html` |

---

## 🧪 Testing:

1. **Extract page 2** using one of the methods above
2. **Save to:** `frontend/images/academic/calendar-page2.jpg`
3. **Open dashboard** in browser
4. **See** the Academic Calendar slider showing your image
5. **Click** the image → Full PDF opens
6. **Hover** over image → See zoom effect

---

## ⚠️ Troubleshooting:

**Image not showing?**
- Check file is at: `frontend/images/academic/calendar-page2.jpg`
- Check filename is exact (no spaces, lowercase)
- Hard refresh browser (Ctrl + Shift + R)

**PDF not opening when clicked?**
- Check PDF is at: `frontend/documents/acad_cal.pdf`
- Check browser allows pop-ups
- Try different browser

**Extractor tool not working?**
- Make sure you have internet (needs PDF.js library)
- Use Chrome or Edge browser
- Try screenshot method instead

---

## 🎉 You're All Set!

The Academic Calendar is now integrated with:
- ✅ Image from PDF page 2
- ✅ Auto-sliding with other content
- ✅ Click to open full PDF
- ✅ Professional hover effects
- ✅ Fallback if image missing

**Next:** Extract the image and place it in the correct folder! 🚀
