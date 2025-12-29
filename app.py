import os
from flask import Flask, render_template, request, redirect, url_for, session
import google.generativeai as genai
import pdfplumber
from google.api_core.exceptions import ResourceExhausted
from dotenv import load_dotenv
import json

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ------------------ Helpers ------------------

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

Ask 15–20 questions step-by-step.
Return only a numbered list of questions.
"""

    try:
        model = genai.GenerativeModel("gemini-2.0-pro")
        response = model.generate_content(prompt)

        if not response or not response.text:
            return []

        lines = [q.strip() for q in response.text.split("\n") if q.strip()]
        questions = [
            q[q.find(".")+1:].strip() if "." in q else q
            for q in lines
        ]

        return questions[:20]

    except ResourceExhausted:
        return []

    except Exception as e:
        print("Gemini error:", e)
        return []


def evaluate_answer(question, answer, resume_text):
    prompt = f"""
Candidate resume: {resume_text}
Question asked: {question}
Answer given: {answer}

Evaluate professionally.
Return JSON:
{{
"score": <0-10>,
"feedback": "short feedback",
"improved_answer": "better answer"
}}
"""

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        result = model.generate_content(prompt)
        return json.loads(result.text)

    except:
        return {
            "score": 6,
            "feedback": "Good attempt. Add more clarity.",
            "improved_answer": "N/A"
        }

# ------------------ Routes ------------------

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files.get("resume")

        if not file or file.filename == "":
            return render_template("index.html", error="Please upload a resume.")

        os.makedirs("uploads", exist_ok=True)
        path = os.path.join("uploads", file.filename)
        file.save(path)

        resume_text = extract_text_from_pdf(path)
        session["resume"] = resume_text

        questions = generate_interview_questions(resume_text)

        if not questions:
            return render_template(
                "index.html",
                error="⚠️ AI service is busy. Please try again in a few minutes."
            )

        session["questions"] = questions
        session["q_index"] = 0
        session["results"] = []

        return redirect(url_for("questions"))

    return render_template("index.html")


@app.route("/questions", methods=["GET", "POST"])
def questions():
    questions = session.get("questions")

    if not questions:
        return redirect(url_for("index"))

    q_index = session.get("q_index", 0)

    if q_index >= len(questions):
        return redirect(url_for("results"))

    return render_template(
        "questions.html",
        question=questions[q_index],
        q_index=q_index
    )


@app.route("/submit_answer", methods=["POST"])
def submit_answer():
    answer = request.form.get("answer")
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
    app.run(host="0.0.0.0", port=10000)
