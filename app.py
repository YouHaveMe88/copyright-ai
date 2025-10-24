from flask import Flask, render_template, request, jsonify
from urllib.request import urlopen
from bs4 import BeautifulSoup
import openai
import re, os
import datetime, pytz

app = Flask(__name__)

# === KONFIGURASI ===
openai.api_key = os.getenv("OPENAI_API_KEY")

# === UTILITAS ===
def clean_text(html):
    soup = BeautifulSoup(html, "html.parser")
    [s.decompose() for s in soup(["script", "style"])]
    text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()
    return text

def fetch_article(url):
    try:
        html = urlopen(url, timeout=10).read()
        text = clean_text(html)
        return text[:12000]
    except Exception as e:
        print("Error fetch_article:", e)
        return f"[Gagal ambil artikel: {e}]"

def format_text(text):
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    paragraphs, paragraph = [], ""
    for s in sentences:
        paragraph += s + " "
        if len(paragraph) > 200:
            paragraphs.append(paragraph.strip())
            paragraph = ""
    if paragraph:
        paragraphs.append(paragraph.strip())
    return "\n".join(f"<p>{p}</p>" for p in paragraphs)

# === AI SUMMARY/REWRITE ===
def ai_rewrite(text, mode="summarize"):
    if mode == "summarize":
        prompt = f"Ringkas berita berikut agar lebih singkat, jelas, dan tetap informatif:\n\n{text}"
    elif mode == "rewrite":
        prompt = f"Tulis ulang berita berikut agar tetap bermakna sama, tapi dengan gaya baru dan tanpa terdeteksi sebagai salinan:\n\n{text}"

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1000,
    )
    raw = response.choices[0].message["content"].strip()
    return format_text(raw)

# === GENERATE TITLE ===
def ai_generate_title(text):
    prompt = f"Buat judul berita baru yang menarik, singkat (maksimal 12 kata), dan relevan dari teks berikut:\n\n{text}"
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=60,
    )
    return response.choices[0].message["content"].strip().replace('"', '')

# === GENERATE HASHTAGS (ChatGPT-Trend Based) ===
def ai_generate_hashtags(text, include_global=True):
    prompt = f"""
    Analisis teks berita berikut secara mendalam dan buat dua daftar tagar yang relevan dan berpotensi viral.
    
    Pertimbangkan algoritme dan tren terkini di TikTok dan Instagram untuk region Indonesia (dan global jika sesuai).
    Buat kombinasi antara tagar topikal, lifestyle, dan trending umum agar peluang tampil di halaman For You (TikTok) dan Explore (Instagram) lebih besar.

    Buat output seperti berikut:
    🎵 TikTok Hashtags: (maksimal 10)
    📸 Instagram Hashtags: (maksimal 10)
    {'🌍 Global Hashtags: (maksimal 5, opsional)' if include_global else ''}

    Berita:
    {text}

    Pastikan tagar disesuaikan dengan tema berita ini, dan gunakan gaya hashtag yang alami dan populer di 2025.
    """

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_tokens=500,
    )

    raw = response.choices[0].message["content"].strip()
    raw = raw.replace("\n", "<br>").replace("**", "")
    return f"<div style='margin-top:10px'>{raw}</div>"


# === ROUTES ===
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    text_input = data.get("text", "")
    url_input = data.get("url", "")
    mode = data.get("mode", "AI")
    action = data.get("action", "summarize")
    include_global = data.get("include_global", True)

    if url_input:
        text_input = fetch_article(url_input)

    if not text_input:
        return jsonify({"error": "Tidak ada teks atau URL yang valid."})

    if action == "generate_title":
        title = ai_generate_title(text_input)
        return jsonify({"result": f"<h2>{title}</h2>"})
    
        
    elif action == "generate_hashtags":
        hashtags = ai_generate_hashtags(text_input, include_global)
        return jsonify({"result": hashtags})

    if mode == "AI":
        result = ai_rewrite(text_input, action)
    else:
        result = format_text(text_input)

    return jsonify({"result": result})

# === Cache Harian untuk Jadwal AI ===
_cache_day = None
_cache_schedule = None

def ai_schedule():
    global _cache_day, _cache_schedule

    today = datetime.date.today().isoformat()

    # kalau sudah pernah dibuat hari ini → pakai hasil lama
    if _cache_day == today and _cache_schedule:
        return _cache_schedule

    tz = pytz.timezone("Asia/Jakarta")
    now = datetime.datetime.now(tz)
    day = now.strftime("%A")
    time_str = now.strftime("%H:%M")

    prompt = f"""
    Hari ini {day}, jam {time_str} WIB.
    Berdasarkan algoritme terbaru TikTok dan Instagram tahun 2025,
    buat jadwal upload konten yang berpotensi FYP dan trending hari ini.

    Pertimbangkan juga tren mingguan umum TikTok (misalnya weekend lebih santai, weekday lebih produktif).
    
    Jelaskan alasan tiap waktu secara ringkas dan gunakan emoji.
    """

    res = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    )

    result = res.choices[0].message["content"].strip()

    # simpan hasil ke cache untuk hari ini
    _cache_day = today
    _cache_schedule = result
    return result

@app.route("/get_schedule")
def get_schedule():
    data = {"schedule": ai_schedule()}
    return jsonify(data)

@app.route("/schedule")
def schedule_page():
    return render_template("schedule.html")

# if __name__ == "__main__":
#     app.run(debug=True, host="0.0.0.0", port=5000)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

