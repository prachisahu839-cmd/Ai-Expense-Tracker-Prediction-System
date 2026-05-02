import sqlite3
import csv
import pandas as pd
from sklearn.linear_model import LinearRegression
from flask import Flask, render_template, request, redirect, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
import io

app = Flask(__name__)
app.secret_key = "secret123"


# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        budget REAL DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        category TEXT,
        description TEXT,
        date TEXT
    )
    """)

    conn.commit()
    conn.close()


# ---------------- CATEGORY ----------------
def detect_category(description):
    if not description:
        return "Other"

    description = description.lower()

    if any(w in description for w in ["pizza","burger","food","coffee"]):
        return "Food"
    elif any(w in description for w in ["uber","bus","train","petrol"]):
        return "Travel"
    elif any(w in description for w in ["amazon","shopping","mall"]):
        return "Shopping"
    elif any(w in description for w in ["bill","electricity","rent"]):
        return "Bills"

    return "Other"


# ---------------- PREDICTION ----------------
def predict_expense_full(user_id):

    conn = sqlite3.connect("database.db")

    df = pd.read_sql_query(
        "SELECT date, amount FROM expenses WHERE user_id=?",
        conn,
        params=(user_id,)
    )

    conn.close()

    if df.empty or len(df) < 5:
        return None, [], []

    df["date"] = pd.to_datetime(df["date"], errors='coerce')
    df = df.dropna()

    df["month"] = df["date"].dt.to_period("M")
    monthly = df.groupby("month")["amount"].sum().reset_index()

    if len(monthly) < 2:
        return None, [], []

    monthly["num"] = range(len(monthly))

    model = LinearRegression()
    model.fit(monthly[["num"]], monthly["amount"])

    pred = float(model.predict([[len(monthly)]])[0])

    months = monthly["month"].astype(str).tolist()
    values = monthly["amount"].astype(float).tolist()

    months.append("Next Month")
    values.append(round(pred, 2))

    return round(pred, 2), months, values


# ---------------- INSIGHTS ----------------
def smart_insights(user_id):

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
    SELECT category, SUM(amount)
    FROM expenses
    WHERE user_id=?
    GROUP BY category
    """, (user_id,))

    data = cur.fetchall()
    conn.close()

    insights = []

    for cat, amt in data:
        if cat == "Food" and amt > 3000:
            insights.append("🍕 High spending on Food")
        elif cat == "Shopping" and amt > 5000:
            insights.append("🛍 Too much Shopping")
        elif cat == "Travel" and amt > 2000:
            insights.append("🚗 Travel cost is high")

    return insights if insights else ["✅ Spending looks balanced"]


# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("home.html")


# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        hashed = generate_password_hash(password)

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        cur.execute("INSERT INTO users(username,password) VALUES (?,?)",
                    (username, hashed))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        cur.execute("SELECT id,password FROM users WHERE username=?", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session["user_id"] = user[0]
            return redirect("/dashboard")

        return "Invalid Login"

    return render_template("login.html")


# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM expenses WHERE user_id=?", (session["user_id"],))
    expenses = cur.fetchall()

    cur.execute("SELECT SUM(amount) FROM expenses WHERE user_id=?", (session["user_id"],))
    total = cur.fetchone()[0] or 0

    cur.execute("SELECT budget FROM users WHERE id=?", (session["user_id"],))
    budget = cur.fetchone()[0] or 0

    cur.execute("""
    SELECT category, SUM(amount)
    FROM expenses
    WHERE user_id=?
    GROUP BY category
    """, (session["user_id"],))

    data = cur.fetchall()
    categories = [x[0] for x in data]
    amounts = [float(x[1]) for x in data]

    conn.close()

    prediction, _, _ = predict_expense_full(session["user_id"])
    insights = smart_insights(session["user_id"])

    return render_template("dashboard.html",
                           expenses=expenses,
                           total=total,
                           budget=budget,
                           categories=categories,
                           amounts=amounts,
                           prediction=prediction,
                           insights=insights)


# ---------------- ADD ----------------
@app.route("/add", methods=["GET","POST"])
def add():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        amount = float(request.form.get("amount"))
        desc = request.form.get("description")
        date = request.form.get("date")

        category = detect_category(desc)

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO expenses(user_id,amount,category,description,date)
        VALUES (?,?,?,?,?)
        """, (session["user_id"], amount, category, desc, date))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("add_expense.html")


# ---------------- DELETE ----------------
@app.route("/delete/<int:id>")
def delete(id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("DELETE FROM expenses WHERE id=? AND user_id=?",
                (id, session["user_id"]))

    conn.commit()
    conn.close()

    return redirect("/dashboard")


# ---------------- SET BUDGET ----------------
@app.route("/set_budget", methods=["POST"])
def set_budget():

    if "user_id" not in session:
        return redirect("/login")

    budget = request.form.get("budget")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("UPDATE users SET budget=? WHERE id=?",
                (budget, session["user_id"]))

    conn.commit()
    conn.close()

    return redirect("/dashboard")


# ---------------- CSV ----------------
@app.route("/upload", methods=["POST"])
def upload():

    if "user_id" not in session:
        return redirect("/login")

    file = request.files.get("file")

    reader = csv.reader(file.read().decode("utf-8").splitlines())
    next(reader, None)

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    for row in reader:
        try:
            date, amount, desc = row
            category = detect_category(desc)

            cur.execute("""
            INSERT INTO expenses(user_id,amount,category,description,date)
            VALUES (?,?,?,?,?)
            """, (session["user_id"], float(amount), category, desc, date))
        except:
            continue

    conn.commit()
    conn.close()

    return redirect("/dashboard")


# ---------------- REPORT ----------------
@app.route("/report")
def report():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
    SELECT category, SUM(amount)
    FROM expenses
    WHERE user_id=?
    GROUP BY category
    """, (session["user_id"],))

    data = cur.fetchall()
    conn.close()

    categories = [x[0] for x in data]
    amounts = [float(x[1]) for x in data]

    return render_template("report.html",
                           categories=categories,
                           amounts=amounts)


# ---------------- PDF ----------------
@app.route("/download_report")
def download_report():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
    SELECT category, SUM(amount)
    FROM expenses
    WHERE user_id=?
    GROUP BY category
    """, (session["user_id"],))

    data = cur.fetchall()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()

    content = [Paragraph("Expense Report", styles["Title"]), Spacer(1,10)]

    table_data = [["Category","Amount"]]
    for row in data:
        table_data.append([row[0], f"₹{row[1]}"])

    content.append(Table(table_data))
    doc.build(content)

    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="report.pdf")


# ---------------- PREDICT ----------------
@app.route("/predict")
def predict():

    if "user_id" not in session:
        return redirect("/login")

    prediction, months, values = predict_expense_full(session["user_id"])

    #  FIX (VERY IMPORTANT)
    if months is None:
        months = []
    if values is None:
        values = []

    return render_template("predict.html",
                           prediction=prediction,
                           months=months,
                           values=values)


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- RUN ----------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)