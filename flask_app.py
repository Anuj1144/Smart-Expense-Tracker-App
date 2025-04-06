from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_babel import Babel, _
import requests
from datetime import datetime, timedelta
import random
import re

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

# Add get_locale to the Jinja2 environment
app.jinja_env.globals['get_locale'] = get_locale

@app.route('/set_language/<lang>')
def set_language(lang):
    session['lang'] = lang
    return redirect(request.referrer or url_for('home_endpoint'))

# Simulated user data
# Simulated user data
users = {
    "user1": {
        "password": "password123",
        "pin": "1234",
        "email": "user1@example.com",
        "phone": "1234567890",
        "notifications_enabled": True
    }
}

# Simulated AI tip generator
def generate_ai_tip():
    try:
        response = requests.get('http://127.0.0.1:8000/expenses')
        response.raise_for_status()
        expenses = response.json().get('expenses', [])
        category_totals = {}
        for expense in expenses:
            category = expense['category']
            amount = float(expense['amount'])
            category_totals[category] = category_totals.get(category, 0) + amount
        if category_totals:
            highest_category = max(category_totals, key=category_totals.get)
            highest_amount = category_totals[highest_category]
            if highest_amount > 500:
                return _(f"You've spent ₹{highest_amount} on {highest_category}. Consider reducing spending in this category!")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching expenses for AI tip: {e}")
    tips = [
        _("Consider reducing dining out to save more this month!"),
        _("Your transport expenses are high. Try carpooling!"),
        _("Set a budget for entertainment to avoid overspending."),
        _("You're doing great! Keep tracking your expenses.")
    ]
    return random.choice(tips)

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('home_endpoint'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        pin = request.form['pin']

        if username in users and users[username]["password"] == password and users[username]["pin"] == pin:
            session['user_id'] = username
            flash(_('Login successful!'), 'success')
            return redirect(url_for('home_endpoint'))
        else:
            flash(_('Invalid username, password, or PIN.'), 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash(_('You have been logged out.'), 'success')
    return redirect(url_for('login'))

@app.route('/home')
def home_endpoint():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        # Fetch expenses
        response = requests.get('http://127.0.0.1:8000/expenses')
        response.raise_for_status()
        expenses = response.json().get('expenses', [])

        # Fetch budget
        budget_response = requests.get('http://127.0.0.1:8000/budget')
        budget_response.raise_for_status()
        budget = budget_response.json().get('budget', 0)

        # Calculate total spent
        total_spent = sum(float(expense['amount']) for expense in expenses)

        # Calculate category totals
        category_totals = {}
        for expense in expenses:
            category = expense['category']
            amount = float(expense['amount'])
            category_totals[category] = category_totals.get(category, 0) + amount

        # Fetch history
        history_response = requests.get('http://127.0.0.1:8000/history')
        history_response.raise_for_status()
        history_data = history_response.json()
        history = history_data.get('history', {})
        daily_totals = history_data.get('daily_totals', {})

        # Calculate savings streak
        streak = 0
        today = datetime.now().date()
        threshold = 100  # Daily spending threshold for a "saving" day
        current_date = today
        while True:
            date_str = current_date.strftime('%Y-%m-%d')
            daily_total = daily_totals.get(date_str, 0)
            if daily_total <= threshold:
                streak += 1
            else:
                break
            current_date -= timedelta(days=1)

        # Generate AI tip
        ai_tip = generate_ai_tip()

        return render_template('home.html', total_spent=total_spent, budget=budget,
                              category_totals=category_totals, streak=streak,
                              history=history, daily_totals=daily_totals, ai_tip=ai_tip)
    except requests.exceptions.RequestException as e:
        flash(_('Error fetching data. Please try again later.'), 'danger')
        print(f"Error in home_endpoint: {e}")
        return render_template('home.html', total_spent=0, budget=0,
                              category_totals={}, streak=0, history={}, daily_totals={}, ai_tip="")

@app.route('/add', methods=['GET', 'POST'])
def add_expense():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        expense = {
            "amount": request.form['amount'],
            "description": request.form['description'],
            "category": request.form['category'],
            "transaction_type": request.form['transaction_type'],
            "date": request.form['date']
        }
        try:
            response = requests.post('http://127.0.0.1:8000/add_expense', json=expense)
            response.raise_for_status()
            flash(_('Expense added successfully!'), 'success')
        except requests.exceptions.RequestException as e:
            flash(_('Error adding expense.'), 'danger')
            print(f"Error adding expense: {e}")
        return redirect(url_for('home_endpoint'))
    return render_template('add_expense.html')  # Changed from 'add.html'
@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        response = requests.get('http://127.0.0.1:8000/history')
        response.raise_for_status()
        history_data = response.json()
        print("History Data:", history_data)
        history = history_data.get('history', {})
        daily_totals = history_data.get('daily_totals', {})
    except requests.exceptions.RequestException as e:
        flash(_('Error fetching history data. Please try again later.'), 'danger')
        print(f"Error fetching history: {e}")
        return render_template('history.html', history={}, daily_totals={})

    return render_template('history.html', history=history, daily_totals=daily_totals)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'file' not in request.files:
            flash(_('No file part in the request'), 'danger')
            return redirect(url_for('upload'))

        file = request.files['file']
        if file.filename == '':
            flash(_('No file selected'), 'danger')
            return redirect(url_for('upload'))

        try:
            files = {'file': (file.filename, file.stream, file.content_type)}
            # Pass the current language to the backend
            current_lang = get_locale()
            # Update the port to 8001
            response = requests.post(
                'http://127.0.0.1:8001/upload_statement',
                files=files,
                headers={'Accept-Language': current_lang}
            )
            print(f"Backend response status: {response.status_code}")
            response.raise_for_status()
            result = response.json()
            print(f"Backend response: {result}")
            flash(result.get('message', _('File processed successfully')), 'success')
            return redirect(url_for('history'))
        except requests.exceptions.ConnectionError as e:
            flash(_('Error: Backend server is not running. Please ensure the backend is running on port 8001.'), 'danger')
            print(f"ConnectionError: {e}")
            return redirect(url_for('upload'))
        except requests.exceptions.HTTPError as e:
            flash(_('Error: Backend returned an error. Check the backend logs for details.'), 'danger')
            print(f"HTTPError: {e}")
            print(f"Response text: {e.response.text if e.response else 'No response'}")
            return redirect(url_for('upload'))
        except requests.exceptions.RequestException as e:
            flash(_('Error uploading file. Please try again.'), 'danger')
            print(f"RequestException: {e}")
            return redirect(url_for('upload'))

    return render_template('upload.html')
@app.route('/parse_sms', methods=['GET', 'POST'])
def parse_sms_endpoint():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        sms_message = request.form['sms_message']
        pattern = r"Debited INR (\d+\.?\d*) for ([\w\s]+) on (\d{4}-\d{2}-\d{2})"
        match = re.match(pattern, sms_message)
        if match:
            amount, description, date = match.groups()
            expense = {
                "amount": amount,
                "description": description,
                "category": "unknown",
                "transaction_type": "Card",
                "date": date
            }
            # Categorize based on description
            description_lower = description.lower()
            if "food" in description_lower or "lunch" in description_lower:
                expense["category"] = "food"
            elif "transport" in description_lower or "fuel" in description_lower:
                expense["category"] = "transport"
            elif "entertainment" in description_lower or "movie" in description_lower:
                expense["category"] = "entertainment"
            try:
                response = requests.post('http://127.0.0.1:8000/add_expense', json=expense)
                response.raise_for_status()
                flash(_('SMS parsed and expense added successfully!'), 'success')
            except requests.exceptions.RequestException as e:
                flash(_('Error parsing SMS.'), 'danger')
                print(f"Error parsing SMS: {e}")
        else:
            flash(_('Could not parse SMS. Ensure the format is: "Debited INR <amount> for <description> on <YYYY-MM-DD>"'), 'danger')
        return redirect(url_for('home_endpoint'))
    return render_template('parse_sms.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_data = users.get(session['user_id'], {})
    if request.method == 'POST':
        users[session['user_id']] = {
            "password": request.form['password'],
            "pin": user_data.get('pin', '1234'),  # Keep the existing PIN
            "notifications_enabled": 'notifications' in request.form,
            "email": request.form['email'],
            "phone": request.form['phone']
        }
        flash(_('Profile updated successfully!'), 'success')
        return redirect(url_for('home_endpoint'))
    return render_template('profile.html', user_data=user_data)

@app.route('/set_budget', methods=['POST'])
def set_budget():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    budget = {"amount": request.form['budget']}
    try:
        response = requests.post('http://127.0.0.1:8000/set_budget', json=budget)
        response.raise_for_status()
        flash(_('Budget set successfully!'), 'success')
    except requests.exceptions.RequestException as e:
        flash(_('Error setting budget.'), 'danger')
        print(f"Error setting budget: {e}")
    return redirect(url_for('home_endpoint'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)