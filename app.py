import streamlit as st
import os, json, time, concurrent.futures
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

# --- 页面配置 ---
st.set_page_config(
    page_title="DeepGraph Pro",
    layout="wide",
    page_icon="☁️",
    initial_sidebar_state="expanded"
)

# --- 未来感样式 ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
:root {
    --bg1: #0f172a; --bg2: #111827; --card: rgba(255,255,255,0.08);
    --border: rgba(255,255,255,0.18); --primary: #5b8cff; --accent: #00d1ff;
}
.stApp {
    background: radial-gradient(120% 120% at 20% 20%, rgba(91,140,255,0.25), transparent 40%),
                radial-gradient(100% 100% at 80% 0%, rgba(0,209,255,0.18), transparent 45%),
                linear-gradient(135deg, var(--bg1), var(--bg2));
    color: #e5e7eb; font-family: 'Inter', sans-serif;
}
.glass-card {
    background: var(--card); border: 1px solid var(--border);
    backdrop-filter: blur(16px) saturate(1.4); -webkit-backdrop-filter: blur(16px) saturate(1.4);
    box-shadow: 0 20px 60px rgba(0,209,255,0.16), 0 8px 24px rgba(0,0,0,0.28);
    border-radius: 16px; padding: 20px 20px 16px; transition: all 180ms ease;
}
.glass-card:hover { transform: translateY(-2px); box-shadow: 0 16px 40px rgba(0,0,0,0.32), 0 20px 60px rgba(0,209,255,0.16); }
.stButton > button, .stDownloadButton > button {
    background: linear-gradient(120deg, var(--primary), var(--accent));
    color:#fff; border:none; border-radius:10px; height:44px; font-weight:700; letter-spacing:0.2px;
    box-shadow:0 10px 30px rgba(91,140,255,0.35); transition:all 150ms ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { filter: brightness(1.06); box-shadow:0 14px 34px rgba(0,209,255,0.35); transform: translateY(-1px); }
.stTextInput > div > div > input, .stTextArea > div > textarea, .stSelectbox > div > div > div {
    background: rgba(255,255,255,0.06) !important; border: 1px solid var(--border) !important;
    border-radius: 10px !important; color: #e5e7eb !important;
}
.stProgress > div > div { background: rgba(255,255,255,0.08); border-radius: 999px; }
.stProgress > div > div > div { background: linear-gradient(120deg, var(--primary), var(--accent)); box-shadow: 0 4px 16px rgba(91,140,255,0.4); }
</style>
""", unsafe_allow_html=True)

# --- 状态管理 ---
if 'processed' not in st.session_state: st.session_state.processed = False
if 'graph_html' not in st.session_state: st.session_state.graph_html = ""
if 'report_txt' not in st.session_state: st.session_state.report_txt = ""
if 'truncated' not in st.session_state: st.session_state.truncated = False

# --- 参数 ---
MAX_WORKERS = 4
CHUNK_LEN = 12000
OVERLAP = 800
BAN_REL = {"是","有","存在","包含","涉及"}  # 过于空泛的谓语，可调整
ALIASES = {
    "邓小平": ["小平", "邓公"],
    "毛泽东": ["毛主席", "毛泽东主席"],
    "习近平": ["习", "近平"],
    # 可继续扩展重要主体/机构/事件
}

COLORS = {
    "HighRisk": "#ff6b6b",
    "Person": "#5b8cff",
    "Outcome": "#94a3b8",
    "Faction": "#a78bfa",
    "NoRisk": "#22c55e",
    "Unknown": "#adb5bd"
}
STYLE = {
    "active": {"color": "#adb5bd", "dashes": False},
    "passive": {"color": "#6c757d", "dashes": True}
}

PROMPT = """
【任务】提取 SVO（有向）三元组。Head=发起者（主动），Tail=承受者（被动）。
【方向】direction=active（Head 主动作用 Tail）或 passive（Head 被 Tail 作用）。
【分类】type ∈ [HighRisk, Faction, Person, Outcome, NoRisk]，不确定用 Unknown。
【格式】JSON 数组：
[{"head": "...", "type_head": "...", "relation": "精确谓语", "tail": "...", "type_tail": "...", "direction": "active|passive"}]
【约束】
1) 不随意合并谓语，保留动词原义。
2) 敏感主体完整表述，不弱化。
3) 无有效三元组则返回 []。
文本（截断）：{text}...
"""

# --- 辅助函数 ---
def split_text(txt, size=CHUNK_LEN, overlap=OVERLAP):
    out = []
    n = len(txt); i = 0
    while i < n:
        out.append(txt[i:i+size])
        i += size - overlap
    return out

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
    except Exception as e:
        print(f"[extract] {file_path} error: {e}")
    return text

def canonicalize(name: str) -> str:
    if not name: return name
    name = name.strip()
    for canon, alias_list in ALIASES.items():
        if name == canon or name in alias_list:
            return canon
    n = "".join(ch for ch in name if ch.isalnum())
    for canon, alias_list in ALIASES.items():
        for a in [canon, *alias_list]:
            if n == "".join(ch for ch in a if ch.isalnum()):
                return canon
    return name

@st.cache_resource
def get_client(api_key): return genai.Client(api_key=api_key)

def analyze_svo(chunk_data, client, model):
    i, text = chunk_data
    prompt = PROMPT.format(text=text[:1200])
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        raw = resp.text.replace("```json","").replace("```","").strip()
        s, e = raw.find('['), raw.rfind(']')+1
        return json.loads(raw[s:e]) if s != -1 else []
    except Exception as e:
        print(f"[chunk {i}] error: {e}")
        return []

def trim_graph(raw, max_nodes=300, min_nodes=50):
    cnt = Counter()
    for it in raw:
        cnt[it["head"]] += 1
        cnt[it["tail"]] += 1
    top_nodes = {n for n, _ in cnt.most_common(max_nodes)}
    trimmed = [it for it in raw if it["head"] in top_nodes and it["tail"] in top_nodes]
    if len(top_nodes) < min_nodes:
        return raw, False
    if len(top_nodes) > max_nodes:
        return trimmed, True
    return trimmed, False

# --- 核心流程 ---
def main_run(files, api_key, model):
    chunks = []
    for f in files:
        txt = extract_text(f)
        if len(txt) > 100:
            for i, s in enumerate(split_text(txt)):
                chunks.append((f"{f.name}-{i}", s))

    if not chunks: return None, "❌ 文件内容为空或读取失败", False

    st.info(f"🚀 云端引擎启动：分析 {len(chunks)} 个片段...")
    bar = st.progress(0)
    raw = []

    client = get_client(api_key)
    max_workers = min(MAX_WORKERS, len(chunks))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = [exe.submit(analyze_svo, c, client, model) for c in chunks]
        for i, f in enumerate(concurrent.futures.as_completed(futures)):
            if res := f.result(): raw.extend(res)
            bar.progress((i+1)/len(chunks))

    if not raw: return None, "❌ 未提取到数据，请检查 API Key 或模型权限", False

    # 归一 + 谓语过滤
    norm = []
    for it in raw:
        h, t, r = canonicalize(it.get("head")), canonicalize(it.get("tail")), it.get("relation")
        if not h or not t or not r: continue
        if r in BAN_REL: continue
        it["head"], it["tail"] = h, t
        norm.append(it)

    # 节点裁剪
    norm, truncated = trim_graph(norm, max_nodes=300, min_nodes=50)

    # 构图
    G = nx.DiGraph()
    for item in norm:
        h, t, r = item["head"], item["tail"], item["relation"]
        ht, tt = item.get("type_head", "Person"), item.get("type_tail", "Person")
        direction = item.get("direction", "active")
        edge_style = STYLE.get(direction, STYLE["active"])
        G.add_node(h, label=h, color=COLORS.get(ht, "#5b8cff"), size=20)
        G.add_node(t, label=t, color=COLORS.get(tt, "#5b8cff"), size=20)
        label = r if len(r) <= 28 else r[:25] + "..."
        G.add_edge(h, t, label=label, color=edge_style["color"], smooth=True, arrows="to", dashes=edge_style["dashes"])

    # 报告
    rpt = "# DeepGraph Report\n\n"
    rpt += f"- 节点数: {len(G.nodes())}\n- 边数: {len(G.edges())}\n"
    type_cnt = Counter([n[1].get('color') for n in G.nodes(data=True)])
    if truncated:
        rpt += "- 注意：节点已截断到前 300 个最相关节点。\n"
    rpt += "- 类型计数（按颜色）: " + ", ".join([f"{k}:{v}" for k,v in type_cnt.items()]) + "\n\n"
    rpt += "## 三元组\n"
    for u, v, d in G.edges(data=True):
        rpt += f"{u} --[{d.get('label','')}]--> {v}\n"

    return G, rpt, truncated

# --- 界面 ---
st.title("DeepGraph Pro (Cloud Edition)")

with st.sidebar:
    st.header("Settings")
    st.success("✅ 云端环境已就绪")
    api_key = st.text_input("Google API Key", type="password")
    model_id = st.text_input("Model ID", value="gemini-2.0-flash-exp")
    if st.button("🔍 Check Available Models"):
        if not api_key:
            st.error("Please enter API Key first")
        else:
            try:
                client = genai.Client(api_key=api_key)
                models = [m.name for m in client.models.list() if "gemini" in m.name]
                st.write(models)
            except Exception as e:
                st.error(f"Error: {e}")

col1, col2 = st.columns([1, 2.2])

with col1:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    files = st.file_uploader("Upload Files (PDF/DOCX/TXT)", accept_multiple_files=True)
    st.markdown("<br>", unsafe_allow_html=True)
    start = st.button("🚀 Start Analysis")
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.processed:
        st.download_button("Download Graph HTML", st.session_state.graph_html, "graph.html", "text/html")
        st.download_button("Download Report TXT", st.session_state.report_txt, "report.txt", "text/plain")

with col2:
    # 状态条
    status = "Ready"
    if start: status = "Running"
    if st.session_state.processed: status = "Done"
    st.markdown(
        f"<div class='glass-card' style='padding:12px 16px; display:flex; gap:8px; align-items:center;'>"
        f"<span style='padding:4px 10px; border-radius:999px; background:rgba(0,209,255,0.16); color:#00d1ff; font-weight:700;'>{status}</span>"
        f"<span style='color:#cbd5e1;'>云端 SVO 图谱分析</span>"
        "</div>", unsafe_allow_html=True
    )

    if start:
        if not api_key or not files:
            st.error("请填入 API Key 并上传文件")
        else:
            with st.spinner("Analyzing on Cloud..."):
                G, rpt, truncated = main_run(files, api_key, model_id)
                if G:
                    net = Network(height="700px", width="100%", bgcolor="#0f172a", font_color="#e5e7eb", directed=True)
                    net.from_nx(G)
                    st.session_state.graph_html = net.generate_html()
                    st.session_state.report_txt = rpt
                    st.session_state.processed = True
                    st.session_state.truncated = truncated
                    st.rerun()
                elif rpt: st.error(rpt)

    if st.session_state.processed:
        if st.session_state.truncated:
            st.warning("⚠️ 节点已截断至前 300 个最相关节点")
        st.components.v1.html(st.session_state.graph_html, height=700)
