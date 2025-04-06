from flask import Flask, request, jsonify, session
from flask_babel import Babel, _
from pymongo import MongoClient
import pytesseract
from PIL import Image
import cv2
import numpy as np
import re
from datetime import datetime, timedelta
import io
import PyPDF2

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Flask-Babel configuration
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
babel = Babel()

# Define the locale selector function
def get_locale():
    return session.get('lang', 'en')

# Initialize Babel with the locale selector
babel.init_app(app, locale_selector=get_locale)

# MongoDB Configuration
client = None
db = None

try:
    print("Attempting to connect to MongoDB...")
    client = MongoClient("mongodb://admin:securepassword123@localhost:27017/")
    db = client["expense_tracker"]
    print("Database initialized successfully with MongoDB. Collections:", db.list_collection_names())
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    raise e

# Collections
expenses_collection = db["expenses"]
budget_collection = db["budget"]

# Set Tesseract path (adjust if necessary)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Flag to ensure budget initialization happens only once
budget_initialized = False

# Initialize budget before the first request (replacement for before_first_request)
@app.before_request
def initialize_budget():
    global budget_initialized
    if not budget_initialized:
        if budget_collection.count_documents({}) == 0:
            budget_collection.insert_one({"amount": 0})
        budget_initialized = True

@app.route('/set_language/<lang>')
def set_language(lang):
    session['lang'] = lang
    return jsonify({"message": _("Language set to ") + lang})

@app.route('/expenses', methods=['GET'])
def get_expenses():
    expenses = list(expenses_collection.find({}, {"_id": 0}))
    return jsonify({"expenses": expenses})

@app.route('/add_expense', methods=['POST'])
def add_expense():
    expense = request.json
    expense["date"] = expense.get("date", datetime.now().strftime("%Y-%m-%d"))
    expense["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Add creation timestamp
    
    # Categorize expense based on description (simple keyword-based categorization)
    description = expense.get("description", "").lower()
    if "food" in description or "lunch" in description or "dinner" in description:
        expense["category"] = "food"
    elif "transport" in description or "fuel" in description or "taxi" in description:
        expense["category"] = "transport"
    elif "entertainment" in description or "movie" in description or "game" in description:
        expense["category"] = "entertainment"
    else:
        expense["category"] = expense.get("category", "other")
    
    expenses_collection.insert_one(expense)
    return jsonify({"message": _("Expense added successfully")})

@app.route('/history', methods=['GET'])
def get_history():
    expenses = list(expenses_collection.find({}, {"_id": 0}))
    history = {}
    daily_totals = {}
    
    for expense in expenses:
        date = expense["date"]
        if date not in history:
            history[date] = []
        history[date].append(expense)
        
        amount = float(expense["amount"])
        daily_totals[date] = daily_totals.get(date, 0) + amount
    
    return jsonify({"history": history, "daily_totals": daily_totals})

@app.route('/budget', methods=['GET'])
def get_budget():
    budget = budget_collection.find_one({}, {"_id": 0})
    return jsonify({"budget": budget.get("amount", 0)})

@app.route('/set_budget', methods=['POST'])
def set_budget():
    budget = request.json
    amount = budget.get("amount")
    budget_collection.update_one({}, {"$set": {"amount": float(amount)}}, upsert=True)
    return jsonify({"message": _("Budget set successfully")})

@app.route('/upload_statement', methods=['POST'])
def upload_statement():
    try:
        if 'file' not in request.files:
            return jsonify({"detail": _("No file part in the request")}), 400
        
        file = request.files['file']
        if not file.filename:
            return jsonify({"detail": _("No file selected")}), 400

        content_type = file.content_type
        transactions = []

        # Reset file stream position to the beginning
        file.stream.seek(0)

        # Extract text from the file
        text = ""
        if "pdf" in content_type:
            # Handle PDF
            pdf_reader = PyPDF2.PdfReader(file.stream)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            print(f"Extracted Text from PDF:\n{text}\n{'-'*50}")
        
        elif "image" in content_type:
            try:
                # Handle Image
                img = Image.open(file.stream)
                # Resize the image to reduce memory usage
                max_size = (1000, 1000)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                img_array = np.array(img)
                if len(img_array.shape) == 3:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                else:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
                
                # Enhanced preprocessing for better OCR accuracy
                gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
                alpha = 2.0  # Increase contrast
                beta = 0
                adjusted = cv2.convertScaleAbs(gray, alpha=alpha, beta=beta)
                denoised = cv2.fastNlMeansDenoising(adjusted)
                thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                kernel = np.ones((3,3), np.uint8)
                dilated = cv2.dilate(thresh, kernel, iterations=2)
                eroded = cv2.erode(dilated, kernel, iterations=1)
                
                # Try Tesseract first
                print("Using Tesseract for text extraction...")
                custom_config = r'--oem 3 --psm 6'
                text = pytesseract.image_to_string(eroded, config=custom_config)
                print(f"Extracted Text from Image (Tesseract):\n{text}\n{'-'*50}")
                
                # If Tesseract fails, try EasyOCR
                if not text.strip() or len(text.strip()) < 10:  # If text is empty or too short
                    print("Tesseract failed to extract meaningful text. Trying EasyOCR...")
                    reader = easyocr.Reader(['en'])
                    result = reader.readtext(eroded)
                    text = '\n'.join([res[1] for res in result])
                    print(f"Extracted Text from Image (EasyOCR):\n{text}\n{'-'*50}")
            except Exception as e:
                print(f"Error processing image: {e}")
                return jsonify({"detail": _("Error processing image. Please ensure the image contains clear text.")}), 400
        
        else:
            return jsonify({"detail": _("Unsupported file type. Please upload a PDF or image.")}), 400

        # Split text into potential bill sections (e.g., separated by "Bill #" or multiple newlines)
        bill_sections = re.split(r'(Bill #\d+|---|\n{2,})', text)
        bill_sections = [section.strip() for section in bill_sections if section.strip() and not re.match(r'(Bill #\d+|---)', section)]
        print(f"Bill Sections: {bill_sections}")

        for section in bill_sections:
            # Non-Business Detection: Filter out non-transactional lines
            lines = section.split('\n')
            filtered_lines = []
            non_business_keywords = ['total', 'header', 'footer', 'statement', 'bank', 'account', 'summary', 'date:', 'number:', 'period:']
            for line in lines:
                line_lower = line.lower()
                if not any(keyword in line_lower for keyword in non_business_keywords) and line.strip():
                    filtered_lines.append(line)
            filtered_text = '\n'.join(filtered_lines)
            print(f"Filtered Text (Section): {filtered_text}")

            # Extract transactions with multiple regex patterns
            patterns = [
                # DD/MM/YYYY Description Amount (with flexible spacing)
                r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+([A-Za-z\s]+?)\s{2,}(\d+\.?\d*)",
                # YYYY-MM-DD Description Amount (with flexible spacing)
                r"(\d{4}-\d{2}-\d{2})\s+([A-Za-z\s]+?)\s{2,}(\d+\.?\d*)",
                # DD-MM-YYYY Description Amount (with flexible spacing)
                r"(\d{1,2}-\d{1,2}-\d{2,4})\s+([A-Za-z\s]+?)\s{2,}(\d+\.?\d*)",
                # Alternative format: DD/MM/YYYY  Description  Amount (with tabs/spaces)
                r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(.+?)\s+(\d+\.?\d*)$",
                # DD-MMM-YYYY format (e.g., 03-Mar-2025)
                r"(\d{1,2}-[A-Za-z]{3}-\d{4})\s+([A-Za-z\s]+?)\s{2,}(\d+\.?\d*)"
            ]
            matches = []
            for pattern in patterns:
                matches.extend(re.findall(pattern, filtered_text, re.IGNORECASE))
            print(f"Regex Matches (Section): {matches}")

            if not matches:
                print("No matches found in this section.")
                continue

            # Process each transaction
            for match in matches:
                date, description, amount = match
                description = description.strip()

                # Date Mismatch: Validate and standardize date
                try:
                    if '/' in date:
                        parsed_date = datetime.strptime(date, '%d/%m/%Y')
                    elif '-' in date and date.count('-') == 2 and date.startswith('20'):
                        parsed_date = datetime.strptime(date, '%Y-%m-%d')
                    elif '-' in date and date.count('-') == 2:
                        parsed_date = datetime.strptime(date, '%d-%b-%Y')
                    else:
                        parsed_date = datetime.strptime(date, '%d-%m-%Y')
                    standardized_date = parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    print(f"Invalid date format for transaction: {date}")
                    continue

                # Validate date (e.g., not in the future beyond today)
                today = datetime.now().date()
                if parsed_date.date() > today:
                    print(f"Date in the future for transaction: {date}")
                    continue

                # Duplicate Bills: Check if the transaction already exists
                existing_transaction = expenses_collection.find_one({
                    "date": standardized_date,
                    "description": description,
                    "amount": amount
                })
                if existing_transaction:
                    print(f"Duplicate transaction found: {date} {description} {amount}")
                    continue

                # Categorize based on description
                transaction = {
                    "date": standardized_date,
                    "description": description,
                    "amount": amount,
                    "category": "unknown",
                    "transaction_type": "Card",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                description_lower = description.lower()
                if "food" in description_lower or "lunch" in description_lower or "grocery" in description_lower:
                    transaction["category"] = "food"
                elif "transport" in description_lower or "fuel" in description_lower or "taxi" in description_lower:
                    transaction["category"] = "transport"
                elif "entertainment" in description_lower or "movie" in description_lower or "online payment" in description_lower:
                    transaction["category"] = "entertainment"
                elif "atm" in description_lower or "withdrawal" in description_lower:
                    transaction["category"] = "withdrawal"

                expenses_collection.insert_one(transaction)
                transactions.append(transaction)

        if not transactions:
            return jsonify({"detail": _("No valid transactions found after processing.")}), 400
        
        return jsonify({"message": _(f"Successfully processed {len(transactions)} transactions"), "transactions": transactions})
    except Exception as e:
        print(f"Unexpected error in upload_statement: {e}")
        return jsonify({"detail": _("Internal server error. Please try again later.")}), 500
@app.route('/analytics/savings_trend', methods=['GET'])
def savings_trend():
    expenses = list(expenses_collection.find({}, {"_id": 0}))
    budget = budget_collection.find_one({}, {"_id": 0}).get("amount", 0)
    monthly_savings = {}
    
    for expense in expenses:
        amount = float(expense["amount"])
        date = expense["date"]
        month = date[:7]  # Extract YYYY-MM
        monthly_savings[month] = monthly_savings.get(month, 0) + amount
    
    # Calculate savings (budget - expenses) per month
    savings_data = {}
    for month, total in monthly_savings.items():
        savings_data[month] = budget - total if budget else 0
    
    return jsonify({"savings_trend": savings_data})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, debug=True)  # Change to 8001