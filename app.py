import json
import os
import glob
import PyPDF2
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from Chatbot import recommend_future, generate_skill_gap, generate_roadmap, get_gemini_response, parse_resume_with_gemini
import markdown

app = Flask(__name__)
app.secret_key = '123'

JSON_FILE = 'users.json'

# Label: Utility Functions (No changes needed here)
def load_users():
    try:
        with open(JSON_FILE, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users):
    with open(JSON_FILE, 'w') as file:
        json.dump(users, file, indent=4)

def load_profile_data_for_user(username: str):
    """Finds and loads the latest resume JSON data for the logged-in user."""
    try:
        search_pattern = os.path.join('parsed_resumes', f'{username}_*.json')
        user_files = glob.glob(search_pattern)
        if not user_files:
            return None
        # Find the most recently modified file
        latest_file = max(user_files, key=os.path.getctime)
        with open(latest_file, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading profile data for {username}: {e}")
        return None

# Label: Core App Routes (Login, Register, Logout)
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users = load_users()
        if username in users and users[username]['password'] == password:
            session['username'] = username
            flash(f'Welcome, {username}! You have successfully logged in.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password. Please try again.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users = load_users()
        if username in users:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register'))
        else:
            users[username] = {'password': password}
            save_users(users)
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been successfully logged out.', 'success')
    return redirect(url_for('login'))

# ====================================================================
# Label: MAJOR PERFORMANCE FIX
# The dashboard route now only READS data, making it load instantly.
# The slow API calls and file writes have been removed from the page load.
# ====================================================================
@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    users = load_users()
    user = users.get(username, {})
    
    # --- Fast Operation: Load existing data ---
    # We only read the profile data from the file. No slow API calls here.
    profile_data = load_profile_data_for_user(username) or {}

    # Get recommendations that were previously saved by another process (like '/generate')
    future_recommendations = profile_data.get('missing_skills', [])
    
    # --- Render the page immediately ---
    return render_template(
        'dashboard.html',
        username=username,
        user=user,
        profile_data=profile_data,
        future_recommendations=future_recommendations
    )

# Label: Asynchronous Data Generation Routes (These are meant to be slow)
# These routes are called by JavaScript in the background after the page has loaded.

@app.route('/generate', methods=['POST'])
def generate():
    """
    Generates the skill gap analysis. Called by JavaScript, not during page load.
    """
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    username = session['username']
    profile_data = load_profile_data_for_user(username)
    if not profile_data:
        return jsonify({'error': 'Profile data not found. Please upload a resume first.'}), 404

    current_skills = profile_data.get('skills', [])
    
    # 1. Slow API call happens here, in the background
    missing_skills = generate_skill_gap(current_skills)

    # 2. Slow file write happens here
    profile_data['missing_skills'] = missing_skills
    
    # Find the latest file to overwrite it
    search_pattern = os.path.join('parsed_resumes', f'{username}_*.json')
    user_files = glob.glob(search_pattern)
    if not user_files:
        return jsonify({'error': 'Could not find a profile file to save to.'}), 404
    
    latest_file = max(user_files, key=os.path.getctime)
    with open(latest_file, 'w') as f:
        json.dump(profile_data, f, indent=4)

    # 3. Return the new skills as a JSON response to the front end
    return jsonify({'skills': missing_skills})


@app.route('/generate_roadmap_data', methods=['POST'])
def generate_roadmap_data():
    """
    Generates the learning roadmap. Called by JavaScript.
    """
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    username = session['username']
    profile_data = load_profile_data_for_user(username)
    if not profile_data:
        return jsonify({'error': 'Profile data not found. Please upload a resume first.'}), 404

    skills_list = profile_data.get('skills', [])
    
    # Slow API call for the roadmap
    roadmap_html = generate_roadmap(username=username, profile_data=profile_data, skills_list=skills_list)
    
    # Save the generated roadmap to the user's profile file
    profile_data['roadmap_html'] = roadmap_html
    
    search_pattern = os.path.join('parsed_resumes', f'{username}_*.json')
    user_files = glob.glob(search_pattern)
    if not user_files:
        return jsonify({'error': 'Could not find a profile file to save to.'}), 404
    
    latest_file = max(user_files, key=os.path.getctime)
    with open(latest_file, 'w') as f:
        json.dump(profile_data, f, indent=4)
        
    return jsonify({'roadmap_html': roadmap_html})


# Label: Resume Upload and Analysis
@app.route('/upload', methods=['POST'])
def upload_resume():
    if 'username' not in session:
        return jsonify({"error": "User not logged in"}), 401
        
    if 'resume' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['resume']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if file:
        try:
            pdf_reader = PyPDF2.PdfReader(file.stream)
            resume_text = "".join(page.extract_text() for page in pdf_reader.pages)
            
            if not resume_text.strip():
                return jsonify({"error": "Could not extract text from PDF."}), 400

            parsed_data = parse_resume_with_gemini(resume_text)

            if "error" in parsed_data:
                return jsonify(parsed_data), 500
            
            username = session['username']
            skills_list = parsed_data.get('skills', [])
            primary_skill = skills_list[0].replace('c++', 'cpp').replace('c#', 'csharp') if skills_list else 'no_skill_found'
            json_filename = f"{username}_{primary_skill}.json"
            
            save_dir = 'parsed_resumes'
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, json_filename)

            with open(save_path, 'w') as json_file:
                json.dump(parsed_data, json_file, indent=4)
            
            return jsonify({
                "message": f"Analysis complete for '{parsed_data.get('name', '')}'.",
                "analysis": parsed_data 
            })

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return jsonify({"error": "An unexpected error occurred during processing."}), 500
            
    return jsonify({"error": "File upload failed"}), 400

# Label: Other Routes (Profile, Chat, etc.)
@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    username = session['username']
    updated_data = request.get_json()
    users = load_users()
    
    if username in users:
        users[username].update(updated_data)
        save_users(users)
        return jsonify({'success': True, 'message': 'Profile updated successfully!', 'user': users[username]})
    
    return jsonify({'success': False, 'error': 'User not found'}), 404

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message')
    ai_response = get_gemini_response(user_message)
    return jsonify({'response': ai_response})

@app.route('/roadmap')
def roadmap():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    username = session['username']
    users = load_users()
    user = users.get(username, {})
    profile_data = load_profile_data_for_user(username)
    
    return render_template(
        'roadmap.html',
        username=username,
        user=user,
        profile_data=profile_data
    )

# Legacy route stubs (can be developed or removed)
@app.route('/generate_recommendations')
def generate_recommendations():
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401

    username = session['username']
    profile_data = load_profile_data_for_user(username) or {}
    skills_list = profile_data.get('skills', [])

    result = recommend_future(username, profile_data, skills_list)
    return jsonify(result)

@app.route("/recommendation")
def recommendation():
    return render_template("recommendation.html")

# Main execution
if __name__ == '__main__':
    app.run(debug=True)