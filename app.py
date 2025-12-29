import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session
import google.generativeai as genai
import pdfplumber

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = str(uuid.uuid4())

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def extract_text_from_pdf(file_path):
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for pg in pdf.pages:
            text += pg.extract_text() or ""
    return text.strip()

def generate_interview_questions(resume_text):
    prompt = f"""
You are a professional tech interviewer. 
Interview the candidate based on this resume:

{resume_text}

Ask 15–20 questions step-by-step, starting with:
- Introduction
- Strengths & weakness
- Projects (easy questions first)
- Basics of programming
- Data structures & algorithms
- Basics of skills mentioned in the resume
- Python basics
- Future goals
- Behavioral questions

Return only a numbered list of questions.
"""
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content(prompt)
    lines = [q.strip() for q in response.text.split("\n") if q.strip()]
    questions = [q[q.find(".")+1:].strip() if "." in q else q for q in lines]
    return questions[:20]

def evaluate_answer(question, answer, resume_text):
    prompt = f"""
Candidate resume: {resume_text}
Question asked: {question}
Answer given: {answer}

Evaluate the answer professionally.
Give JSON as:
{{
"score": <0-10>,
"feedback": "short feedback",
"improved_answer": "better answer"
}}
"""
    model = genai.GenerativeModel("gemini-2.0-flash")
    result = model.generate_content(prompt)
    
    import json
    try:
        data = json.loads(result.text)
        return data
    except:
        return {"score": 6, "feedback": "Good attempt. Add more clarity.", "improved_answer": "N/A"}

@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "POST":
        file = request.files["resume"]
        if not file:
            return "Upload resume"
        
        os.makedirs("uploads", exist_ok=True)
        path = os.path.join("uploads", file.filename)
        file.save(path)

        resume_text = extract_text_from_pdf(path)
        session["resume"] = resume_text

        questions = generate_interview_questions(resume_text)
        session["questions"] = questions
        session["q_index"] = 0
        session["results"] = []

        return redirect(url_for("questions"))

    return render_template("index.html")

@app.route("/questions", methods=["GET","POST"])
def questions():
    q_index = session.get("q_index", 0)
    questions = session.get("questions", [])
    
    if q_index >= len(questions):
        return redirect(url_for("results"))

    current_q = questions[q_index]
    return render_template("questions.html", question=current_q, q_index=q_index)

@app.route("/submit_answer", methods=["POST"])
def submit_answer():
    answer = request.form["answer"]
    q_index = session.get("q_index")
    resume = session.get("resume")
    questions = session.get("questions")

    data = evaluate_answer(questions[q_index], answer, resume)

    session["results"].append({
        "question": questions[q_index],
        "answer": answer,
        "score": data["score"],
        "feedback": data["feedback"],
        "improved_answer": data["improved_answer"]
    })

    session["q_index"] = q_index + 1
    return redirect(url_for("questions"))

@app.route("/results")
def results():
    return render_template("results.html", results=session.get("results", []))

if __name__ == "__main__":
    app.run(debug=True)
