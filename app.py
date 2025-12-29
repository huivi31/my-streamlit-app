import streamlit as st
import os, json, time, concurrent.futures, io, tempfile, re
from collections import Counter
import pypdf
from docx import Document
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from google import genai
from pyvis.network import Network
import networkx as nx

# 社区检测（可选）
try:
    import community as community_louvain
    HAS_LOUVAIN = True
except Exception:
    HAS_LOUVAIN = False

# --- 页面配置 ---
st.set_page_config(
    page_title="DeepGraph Pro",
    layout="wide",
    page_icon="🪐",
    initial_sidebar_state="expanded"
)

# --- 未来感 + 毛玻璃 UI ---
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
:root {
  --bg1:#0c1224; --bg2:#0f1b2f; --card:rgba(255,255,255,0.08);
  --border:rgba(255,255,255,0.16); --primary:#4ae0c8; --accent:#7c6bff; --accent2:#18b4e6;
}
.stApp {
  background:
    radial-gradient(120% 120% at 20% 20%, rgba(74,224,200,0.20), transparent 40%),
    radial-gradient(90% 90% at 80% 0%, rgba(124,107,255,0.18), transparent 42%),
    linear-gradient(145deg, var(--bg1), var(--bg2));
  color:#e6edf7; font-family:'Inter',sans-serif;
}
.glass-card {
  background:var(--card); border:1px solid var(--border);
  backdrop-filter:blur(20px) saturate(1.4); -webkit-backdrop-filter:blur(20px) saturate(1.4);
  box-shadow:0 18px 48px rgba(16,185,240,0.18), 0 18px 48px rgba(124,107,255,0.12);
  border-radius:18px; padding:18px 18px 14px; transition:all 180ms ease;
}
.glass-card:hover { transform:translateY(-2px); box-shadow:0 22px 52px rgba(16,185,240,0.28), 0 22px 52px rgba(124,107,255,0.18); }
.stButton > button, .stDownloadButton > button {
  background:linear-gradient(120deg, var(--primary), var(--accent));
  color:#fff; border:none; border-radius:12px; height:44px; font-weight:700; letter-spacing:0.2px;
  box-shadow:0 14px 30px rgba(72,211,200,0.35); transition:all 140ms ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  filter:brightness(1.06); box-shadow:0 16px 36px rgba(124,107,255,0.35); transform:translateY(-1px);
}
.stTextInput > div > div > input, .stTextArea > div > textarea, .stSelectbox > div > div > div {
  background:rgba(255,255,255,0.06) !important; border:1px solid var(--border) !important;
  border-radius:12px !important; color:#e5e7eb !important;
}
.stProgress > div > div { background:rgba(255,255,255,0.08); border-radius:999px; }
.stProgress > div > div > div {
  background:linear-gradient(120deg, var(--primary), var(--accent2));
  box-shadow:0 6px 18px rgba(72,211,200,0.35);
}
</style>
    """,
    unsafe_allow_html=True,
)

# --- 状态管理 ---
if "processed" not in st.session_state:
    st.session_state.processed = False
if "graph_html" not in st.session_state:
    st.session_state.graph_html = ""
if "report_txt" not in st.session_state:
    st.session_state.report_txt = ""
if "truncated" not in st.session_state:
    st.session_state.truncated = False

# --- 参数（速度 + 精准） ---
MAX_WORKERS = 8
CHUNK_LEN = 3200
OVERLAP = 200
STOP_REL = {"是","有","存在","包含","涉及","包括","进行","开展","属于","位于","担任","任职"}

ALIASES = {
    "邓小平": ["小平", "邓公"],
    "毛泽东": ["毛主席", "毛泽东主席"],
    "习近平": ["习", "近平"],
    # 可扩展
}

COLORS = {
    "Person": "#7c9dff",
    "Org": "#4ae0c8",
    "Event": "#c084fc",
    "Outcome": "#9ca3af",
    "Location": "#22c55e",
    "Unknown": "#94a3b8",
    "HighRisk": "#ff6b6b",
    "NoRisk": "#22c55e",
}
STYLE = {
    "active": {"color": "#bcd7ff", "dashes": False},
    "passive": {"color": "#7f8ea3", "dashes": True},
}

RISK_HIGH = [
    "六四","法轮功","台独","藏独","疆独","颜色革命","颠覆","反党","分裂","群体事件","游行","示威",
    "暴乱","戒严","维稳","镇压","枪击","开枪","抓捕","拘留","逮捕","军机","军演","导弹","核试",
    "机密","泄密","制裁","封锁","封禁","删帖","下架","约谈","审查","封号","黑名单","切断通信","叛逃",
]
RISK_MED = [
    "反腐","调查","处分","整顿","整改","约束","限流","删除","撤稿","禁言","暂停","罚款","打击","查处",
    "问责","召回","停售","关停","停业","封存","管控","封控","隔离","舆情","不当言论","不实信息",
]
ACT_STRONG = [
    "镇压","抓捕","拘留","逮捕","判决","枪击","开枪","封禁","下架","删帖","封号","约谈","驱散",
    "戒严","封锁","切断","围堵","驱逐","开除","免职","查封","停职","审查","封存","禁言","限流",
]

PROMPT = """
你是信息抽取助手，面向政治/历史敏感文本，提取 SVO 有向三元组。
字段: head(主体/发起者), relation(精确谓语), tail(客体/承受者), direction(active|passive),
type_head/type_tail ∈ [Person, Org, Event, Location, Outcome, Unknown]。
仅抽取与敏感事件/高层主体相关的关系：群体事件、反党/颠覆、分裂/独立、重大维稳/封禁/删除/下架/约谈/抓捕、
军政机密/调动、涉外摩擦、高层斗争、反腐大案、重大监管/行业整顿。
第一人称叙述若涉及上述敏感事件或高层主体，也应保留；日常礼节或琐事可忽略。
若文本无敏感事件或重要主体/动作，返回 []。
方向：出现“被/遭/逮捕/拘留/镇压/封禁/删除”等判定 passive，其余 active。
谓语保留原文动词，不用“是/有/进行/开展”等泛化词。
按风险和主体级别排序输出：中央/军委/国家领导人 > 部委/省级 > 地方/个人；高敏感事件 > 中 > 低。

仅依据下列文本，不要使用外部知识（可能被截断）：
{text}
"""

# --- 辅助函数 ---
def split_text(txt, size=CHUNK_LEN, overlap=OVERLAP):
    out = []
    n = len(txt)
    i = 0
    while i < n:
        out.append(txt[i : i + size])
        i += size - overlap
    return out

def extract_text(file_obj):
    file_name = getattr(file_obj, "name", "") or (file_obj if isinstance(file_obj, str) else "")
    ext = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
    if not ext:
        raise ValueError("缺少或不支持的文件扩展名")

    if hasattr(file_obj, "read"):
        data = file_obj.read()
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
    else:
        with open(file_obj, "rb") as f:
            data = f.read()

    text = ""
    try:
        if ext == "pdf":
            reader = pypdf.PdfReader(io.BytesIO(data))
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
        elif ext == "epub":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            try:
                book = epub.read_epub(tmp_path)
                for item in list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT)):
                    soup = BeautifulSoup(item.get_content(), "html.parser")
                    text += soup.get_text() + "\n"
            finally:
                os.remove(tmp_path)
        elif ext in ["docx", "doc"]:
            doc = Document(io.BytesIO(data))
            text = "\n".join([p.text for p in doc.paragraphs])
        else:
            text = data.decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[extract] {file_name} error: {e}")
    return text

def canonicalize(name: str) -> str:
    if not name:
        return name
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

def infer_direction(relation: str, default="active"):
    if not relation:
        return default
    if re.search(r"(被|遭|受|逮捕|拘留|镇压|封禁|删除|下架|驱散|开除|免职|制裁)", relation):
        return "passive"
    return default

def score_event(text_chunk: str, relation: str) -> int:
    score = 0
    def has_any(words):
        return any(w in text_chunk or (relation and w in relation) for w in words)
    if has_any(RISK_HIGH):
        score += 3
    elif has_any(RISK_MED):
        score += 2
    if relation and any(w in relation for w in ACT_STRONG):
        score += 1
    return score

def score_actor(name: str) -> int:
    if not name:
        return 0
    central_kw = ["中央","国务院","军委","全国人大","全国政协","中宣部","中组部","中纪委","政法委","网信办","国安委",
                  "战区","军区","司令部","总部","部委","外交部","国防部","公安部","国安部","发改委","财政部"]
    prov_kw = ["省委","省政府","自治区","直辖市","省军区","武警总队","厅局","省级"]
    local_kw = ["市委","市政府","州政府","县委","县政府","区委","镇政府","街道","乡镇","派出所","基层"]
    if any(k in name for k in central_kw):
        return 3
    if any(k in name for k in prov_kw):
        return 2
    if any(k in name for k in local_kw):
        return 1
    return 0

@st.cache_resource
def get_client(api_key):
    return genai.Client(api_key=api_key)

def analyze_svo(chunk_data, client, model):
    i, text = chunk_data
    prompt = PROMPT.format(text=text)
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        raw = resp.text.replace("```json", "").replace("```", "").strip()
        s, e = raw.find("["), raw.rfind("]") + 1
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
                cid = f"{getattr(f,'name',str(f))}-{i}"
                chunks.append((cid, s))

    if not chunks:
        return None, "❌ 文件内容为空或读取失败", False

    st.info(f"🚀 云端引擎启动：分析 {len(chunks)} 个片段（全量，不截断）...")
    bar = st.progress(0)
    raw = []

    client = get_client(api_key)
    max_workers = min(MAX_WORKERS, len(chunks))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = [exe.submit(analyze_svo, c, client, model) for c in chunks]
        for i, f in enumerate(concurrent.futures.as_completed(futures)):
            if res := f.result():
                raw.extend(res)
            bar.progress((i + 1) / len(chunks))

    if not raw:
        return None, "❌ 未提取到数据，请检查 API Key 或模型权限", False

    # 归一/过滤/评分
    scored = []
    for it in raw:
        h, t, r = canonicalize(it.get("head")), canonicalize(it.get("tail")), it.get("relation")
        if not h or not t or not r:
            continue
        if r in STOP_REL:
            continue
        it["head"], it["tail"] = h, t
        it["direction"] = infer_direction(r, default=it.get("direction", "active"))
        ev_score = score_event("", r)  # 可按需加入 chunk_text
        act_score = max(score_actor(h), score_actor(t))
        total = ev_score + act_score
        it["_score"] = total
        scored.append(it)

    MIN_SCORE = 1
    scored = [it for it in scored if it["_score"] >= MIN_SCORE]
    scored.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # 节点裁剪仅影响展示，不影响抽取
    norm, truncated = trim_graph(scored, max_nodes=300, min_nodes=50)

    # 构图（仅真实抽取边）
    G = nx.DiGraph()
    for item in norm:
        h, t, r = item["head"], item["tail"], item["relation"]
        ht = item.get("type_head", "Person")
        tt = item.get("type_tail", "Person")
        direction = item.get("direction", "active")
        edge_style = STYLE.get(direction, STYLE["active"])
        G.add_node(h, label=h, color=COLORS.get(ht, "#7c9dff"), size=22)
        G.add_node(t, label=t, color=COLORS.get(tt, "#7c9dff"), size=22)
        label = r if len(r) <= 28 else r[:25] + "..."
        G.add_edge(
            h, t,
            label=label,
            color=edge_style["color"],
            smooth=True,
            arrows="to",
            dashes=edge_style["dashes"],
            weight=3.0
        )

    # 社区着色（可选）
    if HAS_LOUVAIN:
        undi = G.to_undirected()
        part = community_louvain.best_partition(undi, weight="weight")
        palette = ["#4ae0c8","#7c9dff","#c084fc","#22c55e","#f59e0b","#ef4444","#8b5cf6","#0ea5e9"]
        for n, comm in part.items():
            G.nodes[n]["color"] = palette[comm % len(palette)]

    # 报告
    rpt = "# DeepGraph Report\n\n"
    rpt += f"- 节点数: {len(G.nodes())}\n- 边数: {len(G.edges())}\n"
    if truncated:
        rpt += "- 注意：节点已截断到前 300 个最相关节点（仅影响展示，抽取未截断）。\n"
    rpt += "## 高分关系（按风险/主体分排序，前 200 条）\n"
    for it in scored[:200]:
        rpt += f"[{it.get('_score',0)}] {it['head']} --[{it['relation']}]--> {it['tail']} ({it.get('direction','active')})\n"

    return G, rpt, truncated

# --- 界面 ---
st.title("DeepGraph Pro · Cloud Edition")

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
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.processed:
        st.download_button("Download Graph HTML", st.session_state.graph_html, "graph.html", "text/html")
        st.download_button("Download Report TXT", st.session_state.report_txt, "report.txt", "text/plain")

with col2:
    status = "Ready"
    if start:
        status = "Running"
    if st.session_state.processed:
        status = "Done"
    st.markdown(
        f"""
        <div class='glass-card' style='padding:12px 16px; display:flex; gap:10px; align-items:center;'>
          <span style='padding:6px 12px; border-radius:999px; background:rgba(74,224,200,0.18); color:#4ae0c8; font-weight:800;'>{status}</span>
          <span style='color:#cbd5e1;'>云端 SVO 图谱分析（敏感优先 · 高速模式）</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if start:
        if not api_key or not files:
            st.error("请填入 API Key 并上传文件")
        else:
            with st.spinner("Analyzing on Cloud..."):
                G, rpt, truncated = main_run(files, api_key, model_id)
                if G:
                    net = Network(
                        height="820px",
                        width="100%",
                        bgcolor="#0c1224",
                        font_color="#e6edf7",
                        directed=True,
                    )
                    net.from_nx(G)
                    net.set_options("""
{
  "physics": {
    "enabled": true,
    "solver": "forceAtlas2Based",
    "forceAtlas2Based": {
      "gravitationalConstant": -160,
      "centralGravity": 0.01,
      "springLength": 110,
      "springConstant": 0.11,
      "damping": 0.9,
      "avoidOverlap": 1.0
    },
    "stabilization": { "enabled": true, "iterations": 1500, "updateInterval": 30 }
  },
  "edges": { "smooth": false },
  "layout": { "improvedLayout": true },
  "interaction": { "dragNodes": true, "hover": true, "navigationButtons": true }
}
                    """)
                    st.session_state.graph_html = net.generate_html()
                    st.session_state.report_txt = rpt
                    st.session_state.processed = True
                    st.session_state.truncated = truncated
                    st.rerun()
                elif rpt:
                    st.error(rpt)

    if st.session_state.processed:
        if st.session_state.truncated:
            st.warning("⚠️ 节点已截断至前 300 个最相关节点（仅影响展示，抽取未截断）")
        st.components.v1.html(st.session_state.graph_html, height=820)
