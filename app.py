from flask import Flask, render_template,request, redirect,session,url_for,flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from google import genai
import os
from datetime import datetime, timezone
import googlemaps


app = Flask(__name__)
app.secret_key = "dude"


#Configure SQL Alchemy
#
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

#Database Models ~ SIngle Row in our DB
class User(db.Model):
    #Class variables
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(25),unique=True, nullable=False)
    password_hash = db.Column(db.String(256),nullable=False)

    def set_password(self,password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self,password):
        return check_password_hash(self.password_hash,password)
    
class Recommendation(db.Model):
    id = db.Column(db.Integer,primary_key=True)
    symptoms = db.Column(db.Text,nullable=False)
    results = db.Column(db.Text,nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete="Cascade"),nullable=False)

class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))
    is_in_house = db.Column(db.Boolean, nullable=False, default=True)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_name = db.Column(db.String(200), nullable=False)
    appointment_datetime = db.Column(db.DateTime,nullable=False)
    status = db.Column(db.String(50), default='Requested',nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    test = db.relationship('Test')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id',ondelete="CASCADE"))
    report_content = db.Column(db.Text, nullable=True)
        
#Routes
@app.route('/complete_appointment/<int:appointment_id>', methods=['POST'])
@login_required
def complete_appointment(appointment_id):
    # Step 1: Get the appointment record and the logged-in user
    appointment = Appointment.query.get_or_404(appointment_id)
    user = User.query.filter_by(username=session['username']).first()

    # Security check: Make sure the appointment belongs to the logged-in user
    if user and appointment.user_id == user.id:
        
        # Step 2: Get the full Test object using the ID from the appointment
        test = Test.query.get(appointment.test_id)

        if test: # Make sure we found a valid test
            # Update the appointment status
            appointment.status = 'Completed'
            
            # --- Generate a simulated report (using the 'test' object) ---
            report_header = f"Results for: {test.name}" # CORRECT: Uses the test name
            report_body = f"This is a simulated report for your test performed at {appointment.clinic_name} on {appointment.appointment_datetime.strftime('%Y-%m-%d')}."
            
            # Add fake "data" based on the test's category
            if "Blood" in test.category: # CORRECT: Uses the test category
                report_data = "\n\nWhite Blood Cell Count: 4.8 (Normal Range: 4.5-11.0)\nRed Blood Cell Count: 5.1 (Normal Range: 4.7-6.1)\nHemoglobin: 15.2 g/dL (Normal Range: 13.5-17.5)"
            elif "Imaging" in test.category: # CORRECT: Uses the test category
                report_data = "\n\nRadiologist's Findings: The diagnostic images show no abnormalities. All structures appear within normal limits."
            else:
                report_data = "\n\nAll results appear to be within normal ranges. Please consult your physician for a full interpretation."

            appointment.report_content = f"{report_header}\n{'-'*20}\n{report_body}\n{report_data}"
            
            db.session.commit()
            flash(f"Results for '{test.name}' are now available!", "success") # CORRECT: Uses the test name
        else:
            flash("Could not find the associated test for this appointment.", "danger")

    return redirect(url_for('dashboard'))
@app.route('/')
def home():
    if "username" in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

#Login Route
@app.route('/login',methods=['GET','POST'])
def login():
    #Collect info from the form
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html',error="The username/password is incorrect or the user is not registered")
    return render_template('login.html')

#Signup Route
@app.route('/sign-up',methods=['GET','POST'])
def sign_up():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user:
            return render_template('login.html', error="User already registered, please login")
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            session['username'] = username
            return redirect(url_for('dashboard'))
    return render_template('sign_up.html')



#Dashboard Route
# In app.py

# In app.py

@app.route('/dashboard')
@login_required
def dashboard():
    username = session['username']
    user = User.query.filter_by(username=username).first()

    # Initialize all the variables we will send to the template
    recommendations_with_details = []
    appointments = []
    stats = {
        'total_appointments': 0,
        'requested_count': 0,
        'completed_count': 0
    }
    upcoming_appointment = None
    completed_reports = []
    if user:
        # --- PART 1: YOUR EXISTING RECOMMENDATION LOGIC (UNCHANGED) ---
        all_tests = Test.query.all()
        tests_by_name = {test.name: test for test in all_tests}
        user_recommendations = Recommendation.query.filter_by(user_id=user.id).order_by(Recommendation.id.desc()).all()
        
        for rec in user_recommendations:
            test_object = tests_by_name.get(rec.results)
            if test_object:
                recommendations_with_details.append({
                    'symptoms': rec.symptoms,
                    'test': test_object
                })

        # --- PART 2: YOUR EXISTING APPOINTMENT LOGIC & NEW STATS LOGIC ---
        # Fetch all appointments for this user
        appointments = Appointment.query.filter_by(user_id=user.id).order_by(Appointment.appointment_datetime.desc()).all()
        
        # Calculate the statistics using the 'appointments' list we just fetched
        stats['total_appointments'] = len(appointments)
        for appt in appointments:
            if appt.status == 'Requested':
                stats['requested_count'] += 1
            elif appt.status == 'Completed':
                stats['completed_count'] += 1
        
        now_utc = datetime.now(timezone.utc)
        upcoming_appointment = Appointment.query.filter(
            Appointment.user_id == user.id,
            Appointment.appointment_datetime > now_utc,
            Appointment.status == 'Requested' # Only show 'Requested' appointments
        ).order_by(Appointment.appointment_datetime.asc()).first()

        completed_reports = Appointment.query.filter_by(
        user_id=user.id, 
        status='Completed'
    ).order_by(Appointment.appointment_datetime.desc()).all()
    

    # --- PART 3: SEND ALL DATA TO THE TEMPLATE ---
    # We are sending all the original data PLUS the new 'stats' dictionary
    return render_template("dashboard.html", 
                           username=username, 
                           recommendations=recommendations_with_details, 
                           appointments=appointments,
                           stats=stats, upcoming_appointment=upcoming_appointment,completed_reports=completed_reports)
#Logout Route
@app.route('/logout')
def logout():
    session.pop('username',None)
    return redirect(url_for('home'))
#Report Route
@app.route('/report/<int:appointment_id>')
@login_required
def view_report(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    # Security check
    if appointment.user.username != session['username']:
        flash("You are not authorized to view this report.", "danger")
        return redirect(url_for('dashboard'))

    return render_template('report.html', appointment=appointment)

#Recommend Route
@app.route('/recommend', methods=['POST'])
@login_required
def recommend():
    all_tests = Test.query.all()
    test_context=""
    for test in all_tests:
        test_context += f"- Test Name: {test.name}, Description: {test.description}\n"
    symptoms_text=request.form['symptoms']
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents = f"""
        You are a helpful medical triage assistant. Your task is to recommend a medical test based on user-provided symptoms.
        Analyze the symptoms below and choose the single most appropriate test from the following list.
        Your entire response must only be the name of the test you choose and nothing else.

        --Avaialble Tests--
        {test_context}
        Symptoms: "{symptoms_text}"
        """
    )
    recommended_test_name = response.text.strip()
    recommended_test = Test.query.filter_by(name=recommended_test_name).first()
    user = User.query.filter_by(username=session['username']).first()

    if user and recommended_test:
        new_recommendation = Recommendation(
            symptoms = symptoms_text,
            results=recommended_test_name,
            user_id = user.id
        )
        db.session.add(new_recommendation)
        db.session.commit()
    else:
        print(f"Could not save recommendation. AI response was: '{recommended_test_name}'")
    
    return redirect(url_for('dashboard'))
    #git
@app.route('/find_clinics')
@login_required
def find_clinics():
    test_name = request.args.get('query','diagnostic lab')
    search_query = f"Diagnostic Labs that perform {test_name} in Brno, Czechia"

    try:
        gmaps = googlemaps.Client(key=os.environ.get("MAPS_API_KEY"))
        places_result = gmaps.places(query=search_query)
        nearby_clinics = places_result.get('results',[])

    except Exception as e:
        print(f"An error occured with Google Maps API: {e}")
        nearby_clinics=[]
    
    maps_api_key = os.environ.get("MAPS_API_KEY")
    return render_template('clinics.html', clinics = nearby_clinics,search_query=search_query,maps_api_key=maps_api_key)

@app.route('/schedule',methods=['POST','GET'])
@login_required
def schedule_appointment():
    clinic_name = request.args.get('clinic_name')

    if request.method == 'POST':
        test_id = request.form['test_id']
        date_str = request.form['date']
        time_str = request.form['time']
        appointment_dt_str = f"{date_str} {time_str}"
        appointment_datetime = datetime.strptime(appointment_dt_str, '%Y-%m-%d %H:%M')

        user = User.query.filter_by(username=session['username']).first()
        new_appointment = Appointment(
            clinic_name=clinic_name,
            appointment_datetime=appointment_datetime,
            test_id=test_id,
            user_id = user.id
        )
        db.session.add(new_appointment)
        db.session.commit()

        flash(f"Your appointment request for {clinic_name} has been submitted!", "success")
        return redirect(url_for('dashboard'))
    test_id = request.args.get('test_id')
    test = Test.query.get(test_id)
    clinic_name = request.args.get('clinic_name')
    return render_template('schedule.html', clinic_name=clinic_name,test=test)





if __name__ == '__main__':
    with app.app_context():
        db.drop_all()
        db.create_all()
        if not Test.query.first():
            print("Test table is empty. Seeding with initial data...")
            initial_tests = [
                    # General Wellness & Blood Tests
                    Test(name="Comprehensive Metabolic Panel", description="Measures glucose level, electrolyte and fluid balance, kidney function, and liver function.", category="Blood Test"),
                    Test(name="Complete Blood Count (CBC)", description="Evaluates your overall health and detects a wide range of disorders, including anemia, infection and leukemia.", category="Blood Test"),
                    Test(name="Lipid Panel", description="Measures fats and fatty substances, including total cholesterol, HDL, LDL, and triglycerides. Key for assessing heart disease risk.", category="Blood Test"),
                    Test(name="HbA1c Test", description="Measures your average blood sugar levels over the past 3 months. Used for diagnosing and monitoring diabetes.", category="Blood Test"),
                    Test(name="C-Reactive Protein (CRP), High-Sensitivity", description="Measures a protein that indicates inflammation in the body. A key marker for cardiovascular disease risk.", category="Blood Test"),
                    Test(name="Liver Function Test (LFT)", description="A panel of tests that checks the health of your liver by measuring proteins, liver enzymes, and bilirubin.", category="Blood Test"),

                    # Vitamin & Mineral Panels
                    Test(name="Vitamin D, 25-Hydroxy", description="Measures the level of Vitamin D in the blood to assess for potential deficiency, which can affect bone health and immunity.", category="Blood Test"),
                    Test(name="Iron and TIBC Panel", description="Measures key iron levels and proteins to check for iron deficiency anemia, a common cause of fatigue.", category="Blood Test"),
                    Test(name="Magnesium Test", description="Checks the level of magnesium, an essential mineral for muscle and nerve function.", category="Blood Test"),
                    
                    # Hormone Panels
                    Test(name="Thyroid Panel (TSH)", description="Checks for thyroid gland problems by measuring Thyroid-Stimulating Hormone (TSH). Essential for diagnosing hypo/hyperthyroidism.", category="Blood Test"),
                    Test(name="Cortisol Test", description="Measures the level of cortisol, the body's primary stress hormone. Useful for investigating adrenal gland issues.", category="Blood Test"),
                    Test(name="Testosterone Total Test", description="Measures the total amount of testosterone in the blood, a key male sex hormone.", category="Blood Test"),

                    # Infectious Disease & Allergy
                    Test(name="Urinalysis", description="Used to detect and manage a wide range of disorders, such as urinary tract infections, kidney disease and diabetes.", category="Urine Test"),
                    Test(name="Respiratory Viral Panel", description="Checks for common respiratory viruses like Influenza A/B, and RSV using a nasal or throat swab.", category="Swab Test"),
                    Test(name="Allergy Panel (IgE)", description="Tests for allergic reactions to common substances like pollen, mold, and pet dander by measuring IgE antibodies.", category="Blood Test"),

                    # Cardiology
                    Test(name="Electrocardiogram (ECG/EKG)", description="Records the electrical signal from the heart to check for different heart conditions. Recommended for palpitations or chest pain.", category="Cardiology",is_in_house=False),
                    
                    # Imaging & Consultation
                    Test(name="Chest X-Ray", description="A diagnostic imaging test used to examine the chest and the organs and structures located in the chest.", category="Imaging",is_in_house=False),
                    Test(name="Abdominal Ultrasound", description="A noninvasive procedure used to assess the organs and structures within the abdomen, such as the liver, gallbladder, and kidneys.", category="Imaging",is_in_house=False),
                    Test(name="Neurological Consultation", description="A specialist consultation to evaluate the nervous system's function, often recommended for persistent headaches, dizziness, or numbness.", category="Consultation",is_in_house=False)
                ]
            db.session.bulk_save_objects(initial_tests)
            db.session.commit()
    app.run(debug=True)