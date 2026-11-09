import pandas as pd
import streamlit as st
from google import genai
from google.genai import errors

from qc_assistant import DATA_DIR, DEFAULT_MODEL, ask, build_system_prompt, load_documents

# Public demo runs on a free API key, so keep each visitor's usage small
MAX_QUESTIONS = 15

EXAMPLES = [
    "Berapa batas maksimal kadar air NDC-35?",
    "Hasil kadar air NDC-28 3,6%. Masih masuk spek?",
    "Retained sample NDC-35 disimpan berapa lama?",
    "Customer nemu plastik di sak, severity apa?",
    "Berapa harga NDC-35 per kg?",
]

st.set_page_config(page_title="QC Spec Assistant", page_icon="🧪")


@st.cache_resource
def get_client():
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


@st.cache_data
def get_system_prompt():
    spec, sop = load_documents()
    return build_system_prompt(spec, sop)


st.title("QC Spec Assistant")
st.caption(
    "Tanya jawab spesifikasi produk dan SOP QC untuk pabrik krimer dan susu bubuk. "
    "Jawaban hanya diambil dari dokumen, lengkap dengan sumbernya."
)
st.info(
    "Semua dokumen di demo ini fiktif. Asisten ini bisa salah mengambil angka, "
    "jadi cocokkan jawabannya dengan dokumen sumber di bawah sebelum dipakai. "
    "Jangan masukkan data rahasia, karena pertanyaan dikirim ke Gemini API versi gratis."
)

def has_api_key():
    # st.secrets raises if there's no secrets file at all
    try:
        return "GEMINI_API_KEY" in st.secrets
    except Exception:
        return False


if not has_api_key():
    st.error("GEMINI_API_KEY belum diisi di secrets. Lihat README bagian Run locally.")
    st.stop()

with st.expander("Lihat dokumen sumber"):
    tab_spec, tab_sop = st.tabs(["Spesifikasi produk", "SOP QC"])
    with tab_spec:
        st.dataframe(pd.read_csv(DATA_DIR / "spesifikasi_produk.csv"), hide_index=True)
    with tab_sop:
        st.markdown((DATA_DIR / "sop_qc.md").read_text(encoding="utf-8"))

with st.sidebar:
    st.subheader("Contoh pertanyaan")
    for example in EXAMPLES:
        if st.button(example, width="stretch"):
            st.session_state.pending = example
    st.divider()
    st.caption(
        "Setiap pertanyaan dijawab terpisah, asisten tidak mengingat pertanyaan sebelumnya. "
        f"Batas {MAX_QUESTIONS} pertanyaan per sesi."
    )

if "history" not in st.session_state:
    st.session_state.history = []

for role, text in st.session_state.history:
    with st.chat_message(role):
        st.markdown(text)

typed = st.chat_input("Tulis pertanyaan, misalnya: shelf life FFP-26 berapa?")
question = typed or st.session_state.pop("pending", None)

if question:
    asked = sum(1 for role, _ in st.session_state.history if role == "user")
    if asked >= MAX_QUESTIONS:
        st.warning("Batas pertanyaan untuk sesi ini sudah habis. Muat ulang halaman untuk mulai lagi.")
        st.stop()

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Mencari di dokumen..."):
                model = st.secrets.get("GEMINI_MODEL", DEFAULT_MODEL)
                answer = ask(get_client(), get_system_prompt(), question, model)
        except errors.ClientError as e:
            if e.code == 429:
                answer = "Kuota API demo sedang habis. Coba lagi beberapa menit lagi."
            else:
                answer = "Permintaan ke model gagal. Coba lagi sebentar lagi."
        except errors.APIError:
            answer = "Server model sedang bermasalah. Coba lagi sebentar lagi."
        st.markdown(answer)

    st.session_state.history.append(("user", question))
    st.session_state.history.append(("assistant", answer))
