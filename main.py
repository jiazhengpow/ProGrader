import streamlit as st
from PyPDF2 import PdfReader
import docx
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import json
import os
import random
import requests

# ----------------- AI Mode Selection -----------------
USE_REAL_AI = st.sidebar.checkbox("Use Real AI (Deepseek R1)", value=False)

# Read OpenRouter Deepseek API Key from Replit Secrets
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
st.write("DEBUG: DEEPSEEK_API_KEY =", "SET" if DEEPSEEK_API_KEY else "None")

# ----------------- Guideline Handling -----------------
def extract_text_from_pdf(file):
    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text.strip()
    except:
        return None

def ocr_pdf(file_path):
    images = convert_from_path(file_path)
    text = ""
    for img in images:
        text += pytesseract.image_to_string(img)
    return text.strip()

def extract_text_from_docx(file):
    doc = docx.Document(file)
    return "\n".join([p.text for p in doc.paragraphs])

# ----------------- Template Management -----------------
TEMPLATE_DIR = "templates"
os.makedirs(TEMPLATE_DIR, exist_ok=True)

def list_templates():
    return [f.replace(".json", "") for f in os.listdir(TEMPLATE_DIR) if f.endswith(".json")]

def save_template(name, data):
    with open(os.path.join(TEMPLATE_DIR, f"{name}.json"), "w") as f:
        json.dump(data, f, indent=2)

def load_template(name):
    with open(os.path.join(TEMPLATE_DIR, f"{name}.json"), "r") as f:
        return json.load(f)

def delete_template(name):
    os.remove(os.path.join(TEMPLATE_DIR, f"{name}.json"))

# ----------------- AI Inference -----------------
def get_ai_suggestions_openrouter(task_template, guideline_text, user_text, image_descriptions=None):
    """Call OpenRouter Deepseek R1 API and return option + reasoning"""
    suggestions = {}
    if not DEEPSEEK_API_KEY:
        st.error("Please set DEEPSEEK_API_KEY in Replit Secrets!")
        return {}

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    for q in task_template:
        prompt = f"""
You are a grading assistant.
Guideline:
{guideline_text}

User task description:
{user_text}

Image descriptions:
{', '.join(image_descriptions) if image_descriptions else 'No images'}

Please select the most appropriate answer for the following question based on the guideline and task, and briefly explain your reasoning:
Question: {q['question']}
Options: {', '.join(q['options'])}

Please return in the following format:
Option: <your chosen option>
Reason: <brief explanation>
"""
        payload = {
            "model": "deepseek/deepseek-chat-v3.1:free",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                answer = resp.json()["choices"][0]["message"]["content"].strip()
            else:
                answer = f"Error {resp.status_code}: {resp.text}"
        except requests.exceptions.RequestException as e:
            answer = f"Request Exception: {e}"

        suggestions[q['question']] = answer

    return suggestions

def get_ai_suggestions_mock(task_template):
    """Mock AI: randomly choose an option with a simple reasoning"""
    suggestions = {}
    for q in task_template:
        choice = random.choice(q['options'])
        reason = "This is a mock reason explaining why this option could be chosen."
        suggestions[q['question']] = f"Option: {choice}\nReason: {reason}"
    return suggestions

def get_ai_suggestions(guideline_text, user_text, task_template, image_descriptions=None):
    if USE_REAL_AI:
        return get_ai_suggestions_openrouter(task_template, guideline_text, user_text, image_descriptions)
    else:
        return get_ai_suggestions_mock(task_template)

# ----------------- Streamlit UI -----------------
st.title("📘 ProGrader App - AI Grading")

# --- Step 1: Upload Guideline ---
st.header("Step 1: Upload Guideline")
uploaded_file = st.file_uploader("Upload a guideline (PDF or DOCX)", type=["pdf", "docx"])
guideline_text = ""
if uploaded_file is not None:
    if uploaded_file.name.endswith(".pdf"):
        guideline_text = extract_text_from_pdf(uploaded_file)
        if not guideline_text:
            st.warning("No text found, trying OCR...")
            with open("temp.pdf", "wb") as f:
                f.write(uploaded_file.read())
            guideline_text = ocr_pdf("temp.pdf")
    else:
        guideline_text = extract_text_from_docx(uploaded_file)
    st.subheader("📄 Extracted Guideline Text")
    st.text_area("Content", guideline_text, height=300)

# --- Step 2: Manage Templates ---
st.header("Step 2: Question Templates")
template_mode = st.radio("Choose Action", ["Create New Template", "Load Existing Template", "Delete Template"])

if template_mode == "Create New Template":
    template_name = st.text_input("Template Name")
    st.write("Add questions below:")
    questions = []
    num_q = st.number_input("Number of Questions", min_value=1, max_value=10, value=1)
    for i in range(num_q):
        st.markdown(f"**Question {i+1}**")
        q_text = st.text_input(f"Question Text for Q{i+1}")
        options = st.text_area(f"Options for Q{i+1} (comma-separated)").split(",")
        questions.append({
            "question": q_text,
            "options": [opt.strip() for opt in options if opt.strip()]
        })
    if st.button("💾 Save Template"):
        if template_name and questions:
            save_template(template_name, questions)
            st.success(f"Template '{template_name}' saved!")

elif template_mode == "Load Existing Template":
    templates = list_templates()
    if templates:
        selected_template = st.selectbox("Choose a template", templates)
        if selected_template:
            template_data = load_template(selected_template)
            st.subheader(f"📑 Template: {selected_template}")
            for q in template_data:
                st.write(f"**Q:** {q['question']}")
                st.radio("Select answer:", q["options"], key=q["question"])
    else:
        st.info("No templates available.")

elif template_mode == "Delete Template":
    templates = list_templates()
    if templates:
        selected_delete = st.selectbox("Select template to delete", templates)
        if selected_delete and st.button("❌ Delete"):
            delete_template(selected_delete)
            st.success(f"Template '{selected_delete}' deleted.")
    else:
        st.info("No templates available to delete.")

# --- Step 3: Create Task ---
st.header("Step 3: Create Task for Grading")
task_images = st.file_uploader("Upload images for this task (optional)", type=["png","jpg","jpeg"], accept_multiple_files=True)
user_text = st.text_input("Text Description / User Search Text for this task")
templates_for_task = list_templates()
selected_template_for_task = st.selectbox("Select Template for this task", templates_for_task)

image_descriptions = []
if task_images:
    st.subheader("🖼️ Uploaded Task Images")
    for img in task_images:
        st.image(Image.open(img), caption=img.name, use_container_width=True)
        image_descriptions.append(img.name)

# --- Step 4: Display AI Suggestions ---
st.header("Step 4: AI / Simulated AI Suggestions")
if selected_template_for_task and guideline_text and user_text:
    task_template = load_template(selected_template_for_task)
    if st.button("🤖 Generate AI Suggestions"):
        with st.spinner("Generating AI suggestions..."):
            suggestions = get_ai_suggestions(guideline_text, user_text, task_template, image_descriptions)
        st.session_state["ai_suggestions"] = suggestions

    if "ai_suggestions" in st.session_state:
        st.subheader("💡 AI Suggested Answers")
        for q_text, answer in st.session_state["ai_suggestions"].items():
            st.write(f"**Q:** {q_text}")
            # Separate option and reasoning
            if "\n" in answer:
                option, reason = answer.split("\n", 1)
                st.write(f"**AI Suggestion:** {option.replace('Option:','').strip()}")
                st.write(f"**Reason:** {reason.replace('Reason:','').strip()}")
            else:
                st.write(f"**AI Suggestion:** {answer}")
else:
    st.info("Please make sure to select a template, upload a guideline, and enter task text.")