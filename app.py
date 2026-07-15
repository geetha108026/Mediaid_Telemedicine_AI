from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import difflib, random

app = Flask(__name__)
CORS(app)

def normalize(text): return (text or '').lower().strip()

def fuzzy_contains(text, keyword, cutoff=0.83):
    if keyword in text: return True
    for token in text.split():
        if difflib.SequenceMatcher(a=token, b=keyword).ratio() >= cutoff:
            return True
    return False

SYMPTOM_MAP = {
    "fever": {"weight": 2, "syn": ["high temperature", "pyrexia", "temperature"]},
    "cough": {"weight": 2, "syn": ["dry cough", "wet cough"]},
    "sore throat": {"weight": 1, "syn": ["throat pain"]},
    "runny nose": {"weight": 1, "syn": ["congestion", "stuffy nose", "blocked nose"]},
    "body ache": {"weight": 1, "syn": ["myalgia", "muscle pain"]},
    "chills": {"weight": 1, "syn": []},
    "loss of taste": {"weight": 2, "syn": ["no taste", "ageusia"]},
    "loss of smell": {"weight": 2, "syn": ["no smell", "anosmia"]},
    "breathing difficulty": {"weight": 3, "syn": ["shortness of breath", "difficulty breathing"]},
    "headache": {"weight": 2, "syn": ["head pain"]},
    "nausea": {"weight": 1, "syn": ["queasy"]},
    "vomiting": {"weight": 2, "syn": ["throwing up", "emesis"]},
    "diarrhea": {"weight": 2, "syn": ["loose stools"]},
    "stomach pain": {"weight": 1, "syn": ["abdominal pain", "tummy pain", "cramps"]},
    "chest pain": {"weight": 4, "syn": ["pressure chest", "tightness chest"]},
    "dizziness": {"weight": 2, "syn": ["lightheaded", "vertigo"]},
    "fatigue": {"weight": 1, "syn": ["tired", "exhausted"]},
    "rash": {"weight": 1, "syn": ["hives", "spots"]},
    "sneezing": {"weight": 1, "syn": []},
    "itchy eyes": {"weight": 1, "syn": ["itching eyes"]},
    "joint pain": {"weight": 1, "syn": ["arthralgia", "knee pain", "joint ache"]},
    "burning urination": {"weight": 2, "syn": ["pain urination", "dysuria"]},
    "back pain": {"weight": 1, "syn": ["lower back pain", "lumbar pain"]},
}

CONDITIONS = {
    "Common Cold / Flu": ["fever", "cough", "sore throat", "runny nose", "body ache", "chills", "fatigue"],
    "COVID-19": ["fever", "cough", "loss of taste", "loss of smell", "breathing difficulty", "fatigue"],
    "Migraine": ["headache", "nausea", "vomiting", "sensitivity to light"],
    "Food Poisoning / Gastroenteritis": ["vomiting", "diarrhea", "stomach pain", "fever"],
    "Allergy (Allergic Rhinitis / Dermatitis)": ["sneezing", "itchy eyes", "runny nose", "rash"],
    "Possible Heart Issue": ["chest pain", "breathing difficulty", "dizziness", "fatigue"],
    "UTI (Urinary Tract Infection)": ["burning urination", "fever", "stomach pain"],
    "Musculoskeletal Strain": ["back pain", "body ache", "fatigue", "joint pain"],
}

EMERGENCY_TRIGGERS = ["chest pain","breathing difficulty","loss of consciousness","confusion","severe bleeding"]

def expand_keywords():
    expanded = {}
    for base, meta in SYMPTOM_MAP.items():
        expanded[base] = set([base] + meta["syn"])
    return expanded

EXPANDED = expand_keywords()

def score_condition(user_text, condition_symptoms):
    score = 0
    for symptom in condition_symptoms:
        matched = False
        if fuzzy_contains(user_text, symptom):
            matched = True
        else:
            for alt in EXPANDED.get(symptom, []):
                if fuzzy_contains(user_text, alt):
                    matched = True
                    break
        if matched:
            score += SYMPTOM_MAP.get(symptom, {"weight":1}).get("weight",1)
    return score

def analyze_symptoms(user_text):
    text = normalize(user_text)
    results = []
    urgent = any(fuzzy_contains(text, trig) for trig in EMERGENCY_TRIGGERS)
    for cond, syms in CONDITIONS.items():
        s = score_condition(text, syms)
        if s > 0:
            results.append((cond, s))
    results.sort(key=lambda x: x[1], reverse=True)
    def tier(score):
        if score >= 6: return "high"
        if score >= 3: return "medium"
        return "low"
    top = [{"condition": c, "score": s, "confidence": tier(s)} for c, s in results[:5]]
    return {"urgent": urgent, "ranked": top}

def classify_phq2(score):
    if score >= 3: return "Positive screen for depressive symptoms (seek evaluation)"
    if score == 2: return "Borderline — consider evaluation"
    return "Negative screen"

def classify_gad2(score):
    if score >= 3: return "Positive screen for anxiety symptoms (seek evaluation)"
    if score == 2: return "Borderline — consider evaluation"
    return "Negative screen"

from flask import render_template

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/diagnose', methods=['POST'])
def api_diagnose():
    data = request.get_json(force=True)
    user_text = data.get('symptoms','')
    analysis = analyze_symptoms(user_text)
    if not analysis["ranked"]:
        summary = "We couldn't match your description to a specific condition. Consider consulting a clinician if symptoms persist or worsen."
    else:
        lines = [f"{r['condition']} — {r['confidence']} confidence (score {r['score']})" for r in analysis['ranked']]
        summary = "\n".join(lines)
    disclaimer = ("This is an educational aid, not a medical diagnosis. "
                  "If symptoms are severe or you feel unsafe, seek urgent care.")
    return jsonify({"urgent": analysis["urgent"], "results": analysis["ranked"], "summary": summary, "disclaimer": disclaimer})

@app.route('/api/mental', methods=['POST'])
def api_mental():
    data = request.get_json(force=True)
    phq2_items = data.get('phq2',[0,0])
    gad2_items = data.get('gad2',[0,0])
    phq2_total = sum(int(x) for x in phq2_items)
    gad2_total = sum(int(x) for x in gad2_items)
    return jsonify({
        "phq2_total": phq2_total,
        "phq2_result": classify_phq2(phq2_total),
        "gad2_total": gad2_total,
        "gad2_result": classify_gad2(gad2_total),
        "note": "Screens are not diagnoses. If positive, consider speaking with a clinician or counselor."
    })

@app.route('/api/book', methods=['POST'])
def api_book():
    data = request.get_json(force=True)
    name = data.get('name','Patient')
    phone = data.get('phone','N/A')
    date = data.get('date','TBD')
    time = data.get('time','TBD')
    appt_id = f"APT{random.randint(10000,99999)}"
    return jsonify({
        "message": f"Appointment booked for {name} on {date} at {time}. We'll call {phone} to confirm.",
        "appointment_id": appt_id
    })

if __name__ == '__main__':
    app.run(debug=True)
