from flask import Flask, render_template, request, redirect, url_for, session, send_file
import os, io, fitz, docx
from openai import OpenAI
from supabase import create_client
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import tempfile

app = Flask(__name__)
app.secret_key = 'supersecret'

# Supabase setup
SUPABASE_URL = "https://huftpqhhzvlouopjblei.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh1ZnRwcWhoenZsb3VvcGpibGVpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQwMDQ0MjMsImV4cCI6MjA1OTU4MDQyM30.uTDR7gD70ym1_3YjtHBKfxkxN_d-beXwW7fyKOwSI0Q"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# OpenRouter setup
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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"
)

@app.route("/")
def home():
    return render_template("home.html")
@app.route("/analyzer", methods=["GET", "POST"])
def analyzer():
    feedback = None
    authorized = False
    students = supabase.table("students").select("*").execute().data
    companies = supabase.table("recruiters").select("*").execute().data

    if request.method == "POST":
        code = request.form.get("code")

        if code == "1234" or any(s["student_id"] == code for s in students):
            authorized = True

            if "student" in request.form:
                student_id = request.form["student"]
                company_name = request.form["company"]
                resume_file = request.files["resume"]

                student = next(s for s in students if s["student_id"] == student_id)
                company = next(c for c in companies if c["Company Name"] == company_name)

                file_bytes = resume_file.read()
                file_type = "pdf" if resume_file.filename.endswith(".pdf") else "docx"

                # Parse the resume
                if file_type == "pdf":
                    doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
                    resume_text = "".join([page.get_text() for page in doc])
                else:
                    doc = docx.Document(io.BytesIO(file_bytes))
                    resume_text = "\n".join([p.text for p in doc.paragraphs])

                # Update the student's resume text in Supabase
                supabase.table("students").update({
                    "resume_text": resume_text
                }).eq("student_id", student_id).execute()

                job_text = company["Job Description"] + "\n" + company["Required Skills"]

                # API call to OpenAI for AI matching analysis
                try:
                    response = client.chat.completions.create(
                        model="deepseek/deepseek-r1:free",
                        messages=[
                            {"role": "system", "content": "You're an expert resume matcher."},
                            {"role": "user", "content": f"Resume:\n{resume_text}\n\nJob:\n{job_text}\n\nGive match %, missing skills, and course suggestions."}
                        ]
                    )

                    # Log the response for debugging
                    print("AI Response:", response)

                    # Check if response is valid
                    if response and hasattr(response, "choices") and response.choices:
                        feedback = response.choices[0].message.content
                        session["report"] = (student, company, feedback)
                    else:
                        feedback = "AI response could not be generated. Please try again."

                except Exception as e:
                    print("AI Error:", e)  # Log the error for debugging
                    feedback = f"AI error occurred: {str(e)}"

            return render_template("analyzer.html", authorized=authorized, students=students, companies=companies, feedback=feedback)

    # In case POST condition isn't met, return the analyzer page with the proper setup
    return render_template("analyzer.html", authorized=authorized, students=students, companies=companies, feedback=feedback)

@app.route("/download_report")
def download_report():
    report_data = session.get("report")

    if report_data is None:
        return "No report data found. Please analyze a resume first.", 400

    student, company, feedback = report_data

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        c = canvas.Canvas(tmp.name, pagesize=A4)
        text = c.beginText(40, 800)
        text.setFont("Helvetica", 12)
        text.textLine("Resume Match Report")
        text.textLine(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        text.textLine(f"Name: {student['name']}")
        text.textLine(f"Email: {student['email']}")
        text.textLine(f"Company: {company['Company Name']}")
        text.textLine("")

        for line in feedback.splitlines():
            text.textLine(line[:100])
        c.drawText(text)
        c.save()

        return send_file(tmp.name, as_attachment=True)

@app.route("/dashboard")
def dashboard():
    students = supabase.table("students").select("*").execute().data
    companies = supabase.table("recruiters").select("*").execute().data
    analyzed_count = sum(1 for s in students if s.get("resume_text"))
    return render_template("dashboard.html", stats={
        "total_students": len(students),
        "total_companies": len(companies),
        "analyzed_count": analyzed_count
    })

@app.route("/uploads", methods=["GET", "POST"])
def uploads():
    if request.method == "POST":
        data = {
            "student_id": request.form.get("student_id"),
            "name": request.form.get("name"),
            "email": request.form.get("email"),
            "cgpa": float(request.form.get("cgpa")),
            "skills": request.form.get("skills"),
        }

        supabase.table("students").insert(data).execute()
        return redirect(url_for("dashboard"))

    return render_template("uploads.html")

if __name__ == "__main__":
    app.run(debug=True)
