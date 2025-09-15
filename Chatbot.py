import google.generativeai as genai
from dotenv import load_dotenv
import os
import glob
import json
import datetime
from typing import Dict, Any
import re
import markdown

# Load environment variables from your .env file
load_dotenv()

# --- FIX 1: Securely load API key from environment variables ---
api_key = ""

    
genai.configure(api_key=api_key)


def get_gemini_response(user_prompt: str) -> str:
    """
    Sends a prompt to the Gemini API with a predefined context.
    """
    try:
        # A more structured prompt
        system_instruction = "You are a helpful career guidance counselor. Your goal is to guide the user's career choices. Keep your responses concise and brief, limited to 3-4 lines."
        
        full_prompt = f"{system_instruction}\n\nUser: {user_prompt}\nResponse:"

        # --- FIX 2: Use a valid model name ---
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(full_prompt)

        return response.text

    except Exception as e:
        print(f"An error occurred in get_gemini_response: {e}")
        return "Sorry, I'm having trouble thinking right now. Please try again."


def load_profile_data_for_user(username: str):
    """Finds and loads the resume JSON data specifically for the logged-in user."""
    try:
        search_pattern = os.path.join('parsed_resumes', f'{username}_*.json')
        user_files = glob.glob(search_pattern)
        if not user_files:
            return None
        latest_file = max(user_files, key=os.path.getctime)
        with open(latest_file, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading profile data for {username}: {e}")
        return None

# You can use the same master skills list to guide the model
MASTER_SKILLS = [
    "python", "java", "c++", "c", "c#", "javascript", "typescript", "go", "rust", "kotlin", "swift", "php", "ruby", "scala",
    "django", "flask", "fastapi", "node.js", "express.js", "ruby on rails", "spring boot",
    "react", "angular", "vue.js", "next.js", "svelte",
    "sql", "mysql", "postgresql", "sqlite", "mongodb", "redis", "cassandra", "elasticsearch",
    "aws", "azure", "google cloud", "gcp", "docker", "kubernetes", "terraform", "ansible", "jenkins", "git", "ci/cd",
    "pandas", "numpy", "scipy", "scikit-learn", "tensorflow", "pytorch", "keras", "matplotlib", "seaborn", "apache spark",
    "html", "css", "sass", "graphql", "rest api",
    "linux", "bash", "powershell", "agile", "scrum"
]


def parse_resume_with_gemini(resume_text: str) -> Dict[str, Any]:
    """
    Parses a resume using the Gemini API to extract key information reliably.
    """
    model = genai.GenerativeModel('gemini-2.5-flash')
    generation_config = {
        "temperature": 0.1,  # Set a low temperature for consistency
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 2048,
    }
    today_date = datetime.date.today().isoformat()
    
    prompt = f"""
    You are an expert resume parsing system. Analyze the resume text and extract information in a structured JSON format.
    Today's date is {today_date}. Use this for roles listed as "Present" or "Current".

    Extract:
    1.  **name**: The full name of the candidate.
    2.  **emails**: A list of all email addresses.
    3.  **phones**: A list of all phone numbers.
    4.  **skills**: A list of skills found ONLY from this master list: {', '.join(MASTER_SKILLS)}
    5.  **experience**: An object with:
        - "total_years": Total years of professional experience.
        - "experience_ranges": A list of all job experiences, each with "start_date", "end_date", and "duration_years".

    Resume Text:
    ---
    {resume_text}
    ---
    """
    
    # --- FIX 3: Use the reliable JSON mode from the API ---
    generation_config = genai.types.GenerationConfig(response_mime_type="application/json")

    try:
        response = model.generate_content(prompt, generation_config=generation_config)
        return json.loads(response.text)
    
    except (json.JSONDecodeError, Exception) as e:
        print(f"An error occurred while parsing the resume: {e}")
        # In case of an error, it's still useful to see the raw text
        try:
            print("--- Raw Response from API ---")
            print(response.text)
        except NameError:
            print("Response object not created.")
        return {"error": "Failed to parse the response from the Gemini API.", "details": str(e)}
    

def format_recommendation_text(text):
    """
    Convert markdown-style * bullets into proper HTML list items.
    """
    # Replace * **something** with <li><b>something</b></li>
    text = re.sub(r"\*{1,2}\s*\*{1,2}(.*?)\*{1,2}", r"<li><b>\1</b></li>", text)

    # Replace single * bullet points into list items
    text = re.sub(r"\*\s*(.*?)($|\n)", r"<li>\1</li>", text)

    # Wrap in <ul> if there are <li> tags
    if "<li>" in text:
        text = f"<ul>{text}</ul>"

    return text


def recommend_future(username, profile_data, skills_list):
    prompt = f"""
    reply in 10 lines


    The following is the profile of a user named {username}.
    
    Profile Data:
    {profile_data}

    Skills:
    {skills_list}

    Based on this, suggest the BEST possible future career path(s),
    next skills to learn, and potential industries or job roles.

    Please respond in short, clear bullet points.
    """

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt, generation_config={"temperature": 0.9})
    

    if response and response.candidates:
        raw_text = response.text
        formatted_text = format_recommendation_text(raw_text)
        return {"username": username, "next_steps": formatted_text}
    else:
        return {"username": username, "next_steps": "No recommendation generated."}




def generate_skill_gap(current_skills):
    """
    Uses the Gemini API to generate a list of missing skills.

    Args:
        current_skills (list): A list of the user's current skills.
        target_role (str): The user's desired job role.

    Returns:
        list: A list of suggested skills to learn.
    """
   

    # --- 1. Create a clear and specific prompt ---
    # Asking for a comma-separated list makes the output easy to parse.
    prompt = f"""
    Based on the following information, identify 2 to 4 crucial missing skills.
    
    Current Skills: {', '.join(current_skills)}
    

    Instructions:
    - Analyze the gap between the current skills and the skills required for the desired job role.
    - Provide a list of the most important skills the user needs to learn.
    - **Return ONLY a comma-separated list of the skill names.** Do not include any explanation, titles, or numbering.

    Example output: TensorFlow, PyTorch, AWS Sagemaker, Kubernetes, Docker, MLOps
    """

    try:
        # --- 2. Call the Gemini API ---
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        
        # --- 3. Parse the response ---
        # The model should return a single string like: "Skill1, Skill2, Skill3"
        generated_text = response.text.strip()
        
        # Split the string into a list and clean up any extra spaces
        missing_skills = [skill.strip() for skill in generated_text.split(',')]
        
        # Filter out any empty strings that might result from parsing
        return [skill for skill in missing_skills if skill]

    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        # Return an empty list as a fallback
        return []



def generate_roadmap(username, profile_data, skills_list):
    """
    Generates a personalized career roadmap using the Gemini model
    and converts it from Markdown to HTML.
    """
    if not skills_list:
        # Returning a dictionary is better for handling errors in the route
        return {"error": "Cannot generate a roadmap without skills. Please analyze a resume first."}

    career_goal = profile_data.get('careerPreferences') or "a more senior role in their field"

    # --- CORRECTED PROMPT ---
    # The instructions are now clear and consistent.
    prompt = f"""
    You are an expert career coach named "Ignite." Your task is to create a detailed, personalized 3-month career roadmap for a user named {username}.

    USER'S PROFILE:
    Current Skills: {', '.join(skills_list)}
    Stated Career Goal: {career_goal}

    INSTRUCTIONS:
    - Create a step-by-step roadmap for the next 3 months.
    - For each month, provide:
        1. A primary focus (e.g., "Mastering Core Concepts").
        2. A bulleted list of specific technical skills or topics to learn.
        3. A suggestion for a small project to apply those skills.
    - **Format your entire response using simple Markdown.** Use headings for each month (e.g., "### Month 1: Foundation") and bullet points for lists.
    """

    try:
        model = genai.GenerativeModel('gemini-2.5-flash') # Corrected to a standard model name
        response = model.generate_content(prompt)
        
        # 1. Get the raw Markdown text from the AI
        raw_markdown_text = response.text
        
        # 2. Convert the Markdown to HTML
        html_output = markdown.markdown(raw_markdown_text)
        
        print("Roadmap generated and converted to HTML successfully.")
        return html_output # Return the final HTML

    except Exception as e:
        print(f"An error occurred in generate_roadmap: {e}")
        return "<p style='color:red;'>Error: Could not generate a roadmap at this time.</p>"



def generate_roadmap_and_challenges(username, profile_data, skills_list):
    """
    Generates a personalized roadmap (Markdown → HTML) 
    and challenges (JSON) using two prompts.
    """

    if not skills_list:
        return {
            "error": "Cannot generate a roadmap without skills. Please analyze a resume first."
        }

    career_goal = profile_data.get('careerPreferences') or "a more senior role in their field"

    # ---------------- FIRST PROMPT (ROADMAP) ----------------
    roadmap_prompt = f"""
    You are an expert career coach named "Ignite." 
    Your task is to create a detailed, personalized 3-month career roadmap for a user named {username}.

    USER'S PROFILE:
    Current Skills: {', '.join(skills_list)}
    Stated Career Goal: {career_goal}

    INSTRUCTIONS:
    - Create a step-by-step roadmap for the next 3 months.
    - For each month, provide:
        1. A primary focus (e.g., "Mastering Core Concepts").
        2. A bulleted list of specific technical skills or topics to learn.
        3. A suggestion for a small project to apply those skills.
    - **Format your entire response using simple Markdown.**
    """

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        roadmap_response = model.generate_content(roadmap_prompt)

        # Raw Markdown text
        roadmap_md = roadmap_response.text

        # Convert Markdown → HTML
        roadmap_html = markdown.markdown(roadmap_md)

    except Exception as e:
        print(f"Error in roadmap generation: {e}")
        return {"error": "Could not generate roadmap"}

    # ---------------- SECOND PROMPT (CHALLENGES) ----------------
    challenges_prompt = f"""
    You are a challenge generator.
    Below is the 3-month roadmap for {username}:

    {roadmap_md}

    Summarize this roadmap into JSON challenges.
    Rules:
    - Strictly output valid JSON (no explanations, no extra text).
    - Structure:
    {{
      "Month 1": [
        {{
          "week": 1,
          "title": "Skill or Project Name",
          "description": "A short practical challenge description",
          "related_skill": "Skill Name"
        }},
        ...
      ],
      "Month 2": [...],
      "Month 3": [...]
    }}
    """

    try:
        challenges_response = model.generate_content(challenges_prompt)
        challenges_json = json.loads(challenges_response.text)
    except Exception as e:
        print(f"Error in challenges generation: {e}")
        challenges_json = {"error": "Could not generate challenges"}

    # ---------------- RETURN BOTH ----------------
    return {
        "roadmap_html": roadmap_html,
        "challenges": challenges_json
    }