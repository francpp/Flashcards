import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import datetime

import logging

# Imposta il logging su INFO e disabilita DEBUG
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Forza il livello di logging per Streamlit e altre librerie
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("watchdog").setLevel(logging.WARNING)  # Se watchdog è la causa
logging.getLogger("urllib3").setLevel(logging.WARNING)   # Se vengono log HTTP

logging.info("L'app è stata avviata!")

# ---- Adattatori e Convertitori per DATE ----
sqlite3.register_adapter(datetime.date, lambda d: d.isoformat())
sqlite3.register_converter("DATE", lambda s: datetime.date.fromisoformat(s.decode()))

# ---- Connessione al database SQLite ----
def get_db_connection():
    return sqlite3.connect("flashcards.db", check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)

conn = get_db_connection()
cursor = conn.cursor()

# ---- Creazione delle tabelle se non esistono ----
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
""")

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

# ---- Funzione per registrare un utente ----
def register_user(username, password):
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
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
    return result[0] if result else None

# ---- Funzione per aggiungere una flashcard ----
def add_flashcard(user_id, english, italian):
    today = datetime.date.today()
    cursor.execute("INSERT INTO flashcards (user_id, english, italian, level, next_review) VALUES (?, ?, ?, ?, ?)",
                   (user_id, english.strip(), italian.strip(), 1, today))
    conn.commit()

# ---- Intervalli di ripasso ----
REVIEW_INTERVALS = {1: 2, 2: 5, 3: 15, 4: 40, 5: 100}

# ---- Funzione per aggiornare il livello di una flashcard ----
def update_level(user_id, word, correct):
    cursor.execute("SELECT level FROM flashcards WHERE user_id=? AND english=?", (user_id, word))
    result = cursor.fetchone()
    
    if result:
        current_level = result[0]
        if correct:
            new_level = min(current_level + 1, 6)
        else:
            new_level = max(current_level - 1, 1)

        next_review = None if new_level == 6 else datetime.date.today() + datetime.timedelta(days=REVIEW_INTERVALS.get(new_level, 1))

        cursor.execute("UPDATE flashcards SET level=?, next_review=? WHERE user_id=? AND english=?",
                       (new_level, next_review, user_id, word))
        conn.commit()

# ---- Funzione per ottenere le frasi da ripassare oggi ----
def get_words_to_review(user_id):
    today = datetime.date.today()
    df = pd.read_sql_query("SELECT * FROM flashcards WHERE user_id=? AND next_review <= ?", conn, params=(user_id, today))
    return df

# ---- UI Streamlit ----
st.title("📚 Flashcard Trainer")

# ---- Gestione login / registrazione ----
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None

if "current_flashcard" not in st.session_state:
    st.session_state["current_flashcard"] = None

if "user_answer" not in st.session_state:
    st.session_state["user_answer"] = ""

if "feedback_message" not in st.session_state:
    st.session_state["feedback_message"] = ""

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
    st.header("➕ Aggiungi una nuova frase")
    with st.form("add_flashcard_form"):
        english_word = st.text_area("Frase in Inglese")
        italian_word = st.text_area("Traduzione in Italiano")
        submit_button = st.form_submit_button("Aggiungi")

        if submit_button:
            if english_word and italian_word:
                add_flashcard(st.session_state["user_id"], english_word, italian_word)
                st.success(f"Aggiunta: {english_word} → {italian_word}")
                st.rerun()
            else:
                st.warning("Inserisci entrambi i campi!")

    # ---- Ripasso delle flashcard ----
    st.header("🔄 Ripassa le frasi")
    words_to_review = get_words_to_review(st.session_state["user_id"])

    if not words_to_review.empty:
        if st.session_state["current_flashcard"] is None:
            st.session_state["current_flashcard"] = words_to_review.sample(1).iloc[0]

        flashcard = st.session_state["current_flashcard"]
        italian_word = flashcard["italian"]
        correct_answer = flashcard["english"]

        st.subheader(f"Come si dice in inglese: **{italian_word}**?")
        user_answer = st.text_area("Scrivi la frase in inglese:", value=st.session_state["user_answer"])

        if st.button("Verifica"):
            if user_answer.strip().lower() == correct_answer.lower():
                st.session_state["feedback_message"] = "✅ Corretto!"
                update_level(st.session_state["user_id"], correct_answer, correct=True)
            else:
                st.session_state["feedback_message"] = f"❌ Sbagliato! La risposta corretta è: {correct_answer}"
                update_level(st.session_state["user_id"], correct_answer, correct=False)

            st.session_state["current_flashcard"] = None
            st.session_state["user_answer"] = ""
            st.rerun()

    else:
        st.info("Nessuna frase da ripassare oggi!")

    st.write(st.session_state["feedback_message"])

    # ---- Seleziona livello per visualizzazione ----
    st.header("📖 Le tue Flashcard")
    selected_level = st.selectbox("Seleziona il livello da visualizzare:", [1, 2, 3, 4, 5, 6])

    def get_flashcards_by_level(user_id, level):
        query = "SELECT english, italian FROM flashcards WHERE user_id = ? AND level = ?"
        df = pd.read_sql_query(query, conn, params=(user_id, level))
        return df

    df_filtered = get_flashcards_by_level(st.session_state["user_id"], selected_level)

    if df_filtered.empty:
        st.info("❕ Nessuna flashcard trovata per questo livello.")
    else:
        st.dataframe(df_filtered, hide_index=True)

    # ---- Download CSV con tutte le flashcard ----
    df_all = get_flashcards_by_level(st.session_state["user_id"], selected_level)
    csv_all = df_all.to_csv(index=False).encode('utf-8')

    st.download_button(label="📥 Scarica tutte le Flashcard (CSV)", data=csv_all, file_name="flashcards_tutte.csv", mime="text/csv")
