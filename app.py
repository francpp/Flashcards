import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import datetime

# ---- Funzione per connettersi al database SQLite ----
def get_db_connection():
    conn = sqlite3.connect("flashcards.db", check_same_thread=False)
    return conn

# ---- Creazione tabelle se non esistono ----
conn = get_db_connection()
cursor = conn.cursor()

# Tabella utenti
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
""")

# Tabella flashcards (associate a ogni utente)
cursor.execute("""
CREATE TABLE IF NOT EXISTS flashcards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    english TEXT,
    italian TEXT,
    level INTEGER DEFAULT 1,
    next_review DATE,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")
conn.commit()

# ---- Funzione per registrare un nuovo utente ----
def register_user(username, password):
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()  # Hash della password
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

# ---- Funzione per autenticare un utente ----
def login_user(username, password):
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    cursor.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, hashed_pw))
    result = cursor.fetchone()
    return result[0] if result else None  # Restituisce user_id se trovato

# ---- Ottieni le flashcards dell'utente ----
def get_flashcards(user_id):
    df = pd.read_sql_query(f"SELECT * FROM flashcards WHERE user_id={user_id}", conn)
    return df

# ---- Aggiungi una flashcard ----
def add_flashcard(user_id, english, italian):
    today = datetime.date.today()
    cursor.execute("INSERT INTO flashcards (user_id, english, italian, level, next_review) VALUES (?, ?, ?, ?, ?)",
                   (user_id, english, italian, 1, today))
    conn.commit()

# ---- Aggiorna il livello di una parola ----
REVIEW_INTERVALS = {1: 2, 2: 5, 3: 15, 4: 40, 5: 100}  # Giorni di ripasso

def update_level(user_id, word, correct):
    cursor.execute("SELECT level FROM flashcards WHERE user_id=? AND english=?", (user_id, word))
    result = cursor.fetchone()
    
    if result:
        current_level = result[0]
        new_level = min(current_level + 1, 6) if correct else max(current_level - 1, 1)
        next_review = None if new_level == 6 else datetime.date.today() + datetime.timedelta(days=REVIEW_INTERVALS.get(new_level, 1))

        cursor.execute("UPDATE flashcards SET level=?, next_review=? WHERE user_id=? AND english=?",
                       (new_level, next_review, user_id, word))
        conn.commit()

# ---- Ottieni parole da ripassare oggi ----
def get_words_to_review(user_id):
    today = datetime.date.today()
    df = pd.read_sql_query(f"SELECT * FROM flashcards WHERE user_id={user_id} AND next_review <= '{today}'", conn)
    return df

# ---- UI Streamlit ----
st.title("📚 Flashcard Trainer")

# ---- Sezione di login / registrazione ----
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None

if st.session_state["user_id"] is None:
    choice = st.sidebar.selectbox("Seleziona:", ["Login", "Registrati"])

    if choice == "Registrati":
        st.sidebar.subheader("📝 Registrazione")
        new_user = st.sidebar.text_input("Username")
        new_pass = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Registrati"):
            if register_user(new_user, new_pass):
                st.success("✅ Registrazione completata! Ora effettua il login.")
            else:
                st.error("❌ Username già esistente!")

    elif choice == "Login":
        st.sidebar.subheader("🔑 Login")
        username = st.sidebar.text_input("Username")
        password = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Accedi"):
            user_id = login_user(username, password)
            if user_id:
                st.session_state["user_id"] = user_id
                st.rerun()
            else:
                st.error("❌ Credenziali errate!")

# ---- Sezione dopo il login ----
else:
    st.sidebar.success("✅ Login effettuato!")
    st.sidebar.button("Esci", on_click=lambda: st.session_state.update({"user_id": None}))

    # ---- Aggiungere flashcard ----
    st.header("➕ Aggiungi una nuova parola")
    english_word = st.text_input("Parola in Inglese")
    italian_word = st.text_input("Traduzione in Italiano")
    if st.button("Aggiungi"):
        if english_word and italian_word:
            add_flashcard(st.session_state["user_id"], english_word.lower(), italian_word.lower())
            st.success(f"Aggiunta: {english_word} → {italian_word}")
        else:
            st.warning("Inserisci entrambi i campi!")

    # ---- Ripasso delle flashcard ----
    st.header("🔄 Ripassa le parole")
    words_to_review = get_words_to_review(st.session_state["user_id"])

    if not words_to_review.empty:
        word_data = words_to_review.sample(1).iloc[0]
        st.subheader(f"Qual è la traduzione di: **{word_data['english']}**?")
        user_answer = st.text_input("Scrivi la traduzione:")

        if st.button("Verifica"):
            correct_answer = word_data["italian"].lower()
            if user_answer.strip().lower() == correct_answer:
                st.success("✅ Corretto!")
                update_level(st.session_state["user_id"], word_data["english"], correct=True)
            else:
                st.error(f"❌ Sbagliato! La risposta corretta è: {correct_answer}")
                update_level(st.session_state["user_id"], word_data["english"], correct=False)
    else:
        st.info("Nessuna parola da ripassare oggi!")

    # ---- Mostra flashcards utente ----
    st.header("📖 Le tue Flashcard")
    df = get_flashcards(st.session_state["user_id"])
    st.write(df)

    # ---- Download CSV ----
    st.header("⬇️ Scarica le tue Flashcard")
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(label="📥 Scarica CSV", data=csv, file_name="flashcards.csv", mime="text/csv")
