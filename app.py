# app.py
import asyncio
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from telethon import TelegramClient
import nest_asyncio

# Aktifkan nest_asyncio untuk menangani event loop
nest_asyncio.apply()

# Buat event loop global
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Konfigurasi dasar
API_ID = '20115110'
API_HASH = '192c9900730edbd7e03fe772e3f8810d'

# Setup path dan direktori
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(BASE_DIR, 'Session')

# Pastikan folder untuk sesi ada dengan permission yang tepat
os.makedirs(SESSION_DIR, exist_ok=True)
os.chmod(SESSION_DIR, 0o777)

app = Flask(__name__)
app.secret_key = 'ManusiaHebat'

# Dictionary untuk menyimpan client
clients = {}

def run_async(coro):
    """Helper function untuk menjalankan coroutine."""
    return loop.run_until_complete(coro)

def cleanup_session(phone_number, session_file):
    """Membersihkan session yang rusak."""
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
        except Exception as e:
            print(f"Error cleaning session: {e}")
    if phone_number in clients:
        client = clients[phone_number]
        run_async(client.disconnect())
        del clients[phone_number]

async def init_client(phone_number, session_file):
    """Inisialisasi client dengan penanganan error yang lebih baik."""
    if phone_number not in clients:
        try:
            client = TelegramClient(session_file, API_ID, API_HASH, loop=loop)
            await client.connect()
            if not await client.is_user_authorized():
                clients[phone_number] = client
            return client
        except Exception as e:
            cleanup_session(phone_number, session_file)
            raise e
    return clients[phone_number]

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        phone_number = request.form.get("phone_number").strip()
        
        # Tambahkan +62 jika nomor tidak dimulai dengan "+"
        if not phone_number.startswith("+"):
            phone_number = "+62" + phone_number
        
        # Buat path session file
        session_file = os.path.join(SESSION_DIR, f"{phone_number.replace('+', '').replace(' ', '')}.session")
        
        try:
            async def send_code():
                client = await init_client(phone_number, session_file)
                if not await client.is_user_authorized():
                    await client.send_code_request(phone_number)
            
            run_async(send_code())
            return redirect(url_for("otp", phone_number=phone_number))
            
        except Exception as e:
            flash(f"Terjadi kesalahan: {str(e)}")
            cleanup_session(phone_number, session_file)
            return redirect(url_for("index"))
    
    return render_template("index.html")

@app.route("/otp/<phone_number>", methods=["GET", "POST"])
def otp(phone_number):
    session_file = os.path.join(SESSION_DIR, f"{phone_number.replace('+', '').replace(' ', '')}.session")
    
    if phone_number not in clients:
        cleanup_session(phone_number, session_file)
        flash("Sesi tidak ditemukan. Mulai ulang.")
        return redirect(url_for("index"))
    
    if request.method == "POST":
        otp = request.form.get("otp").strip()
        client = clients[phone_number]
        
        try:
            async def verify_code():
                await client.sign_in(phone_number, otp)
                user = await client.get_me()
                await client.disconnect()
                return user.first_name if user.first_name else "Pengguna"
            
            user_name = run_async(verify_code())
            flash(f"Tersedia {user_name} ({phone_number}).")
            
            # Bersihkan client
            cleanup_session(phone_number, session_file)
            return redirect(url_for("index"))
            
        except Exception as e:
            flash(f"OTP salah atau terjadi kesalahan: {str(e)}")
            cleanup_session(phone_number, session_file)
            return redirect(url_for("index"))
    
    return render_template("otp.html", phone_number=phone_number)

@app.errorhandler(Exception)
def handle_error(error):
    if "wrong session ID" in str(error).lower():
        phone_number = request.view_args.get('phone_number', '')
        if phone_number:
            session_file = os.path.join(SESSION_DIR, f"{phone_number.replace('+', '').replace(' ', '')}.session")
            cleanup_session(phone_number, session_file)
    flash(f"Terjadi kesalahan: {str(error)}")
    return redirect(url_for("index"))

if __name__ == "__main__":
    try:
        app.run(debug=True)
    finally:
        # Cleanup saat aplikasi berhenti
        for client in clients.values():
            run_async(client.disconnect())
        loop.close()