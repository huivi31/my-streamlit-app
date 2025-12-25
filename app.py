import streamlit as st
import os, json, time, random, threading
import concurrent.futures
from collections import Counter
import pypdf
from docx import Document
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from pyvis.network import Network
import networkx as nx

# --- 1. 页面配置 ---
st.set_page_config(
    page_title="DeepGraph Pro", 
    layout="wide", 
    page_icon="🚀",
    initial_sidebar_state="expanded"
)

# --- 2. 样式优化 ---
st.markdown("""
<style>
    .stApp {
        background-color: #f8f9fa;
        color: #212529;
    }
    .glass-card {
        background: white;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }
    .stButton > button {
        background: #007bff; color: white; border: none; border-radius: 6px; height: 42px; font-weight: 600;
    }
    .stButton > button:hover { background: #0056b3; }
</style>
""", unsafe_allow_html=True)

# --- 3. 状态管理 ---
if 'processed' not in st.session_state: st.session_state.processed = False
if 'graph_html' not in st.session_state: st.session_state.graph_html = ""
if 'report_txt' not in st.session_state: st.session_state.report_txt = ""

# --- 4. 核心功能 ---

def extract_text(file_path):
    ext = file_path.lower().split('.')[-1]
    text = ""
    try:
        if ext == 'pdf':
            reader = pypdf.PdfReader(file_path)
            for page in reader.pages: text += (page.extract_text() or "") + "\n"
        elif ext == 'epub':
            book = epub.read_epub(file_path)
            for item in list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT)):
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text += soup.get_text() + "\n"
        elif ext in ['docx', 'doc']:
            doc = Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
    except: pass
    return text

def analyze_svo(chunk_data):
    i, text, key, model = chunk_data
    client = genai.Client(api_key=key)
    prompt = f"""
    【任务】提取SVO图谱。Head=发起者。
    【分类】[HighRisk], [Faction], [Person], [Outcome], [NoRisk]。
    【格式】JSON: [{{"head": "发起者", "type_head": "类型", "relation": "主动谓语", "tail": "承受者", "type_tail": "类型"}}]
    文本: {text[:1000]}...
    """
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        raw = response.text.replace("```json", "").replace("```", "").strip()
        s, e = raw.find('['), raw.rfind(']') + 1
        return json.loads(raw[s:e]) if s != -1 else []
    except: return []

def main_run(files, api_key, model):
    chunks = []
    for f in files:
        txt = extract_text(f)
        if len(txt) > 100:
            subs = [txt[i:i+60000] for i in range(0, len(txt), 60000)]
            for i, s in enumerate(subs): chunks.append((i, s, api_key, model))
    
    if not chunks: return None, "❌ 读取失败或内容为空"

    st.info(f"🚀 正在分析 {len(chunks)} 个片段...")
    bar = st.progress(0)
    raw = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as exe:
        futures = [exe.submit(analyze_svo, c) for c in chunks]
        for i, f in enumerate(concurrent.futures.as_completed(futures)):
            if res := f.result(): raw.extend(res)
            bar.progress((i+1)/len(chunks))

    if not raw: return None, "❌ 未提取到数据，请检查 Key 权限或更换模型 ID"

    G = nx.DiGraph()
    COLORS = {"HighRisk": "#dc3545", "Person": "#0d6efd", "Outcome": "#6c757d", "Faction": "#6f42c1", "NoRisk": "#198754"}
    
    for item in raw:
        h, t, r = item.get('head'), item.get('tail'), item.get('relation')
        if h and t and r:
            ht, tt = item.get('type_head', 'Person'), item.get('type_tail', 'Person')
            G.add_node(h, label=h, color=COLORS.get(ht, "#0d6efd"), size=20)
            G.add_node(t, label=t, color=COLORS.get(tt, "#0d6efd"), size=20)
            G.add_edge(h, t, label=r, color="#adb5bd")

    rpt = "# DeepGraph Report\n\n"
    for u, v, d in G.edges(data=True):
        rpt += f"{u} --[{d['label']}]--> {v}\n"
        
    return G, rpt

# --- 5. 界面 ---
st.title("DeepGraph Pro (Cloud Edition)")

with st.sidebar:
    st.header("Settings")
    st.info("☁️ 云端部署版: 无需代理，请直接使用 API Key")
    
    api_key = st.text_input("Google API Key", type="password")
    model_id = st.text_input("Model ID", value="gemini-2.0-flash-exp")
    
    if st.button("🔍 Check Models"):
        if not api_key:
            st.error("Please enter API Key")
        else:
            try:
                client = genai.Client(api_key=api_key)
                models = [m.name for m in client.models.list() if "gemini" in m.name]
                st.success("Available Models:")
                st.code("\n".join(models))
            except Exception as e:
                st.error(f"Error: {e}")

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    files = st.file_uploader("Upload Files", accept_multiple_files=True)
    st.markdown("<br>", unsafe_allow_html=True)
    start = st.button("🚀 Start Analysis")
    st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state.processed:
        st.download_button("Download HTML", st.session_state.graph_html, "graph.html", "text/html")
        st.download_button("Download Report", st.session_state.report_txt, "report.txt", "text/plain")

with col2:
    if start:
        if not api_key or not files:
            st.error("Missing API Key or Files")
        else:
            with st.spinner("Analyzing..."):
                G, rpt = main_run(files, api_key, model_id)
                if G:
                    net = Network(height="700px", width="100%", bgcolor="white", font_color="#333", directed=True)
                    net.from_nx(G)
                    st.session_state.graph_html = net.generate_html()
                    st.session_state.report_txt = rpt
                    st.session_state.processed = True
                    st.rerun()
                elif rpt: st.error(rpt)

    if st.session_state.processed:
        st.components.v1.html(st.session_state.graph_html, height=700)
