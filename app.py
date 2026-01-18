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

# 社区检测
try:
    import community as community_louvain
    HAS_LOUVAIN = True
except Exception:
    HAS_LOUVAIN = False

# --- 页面配置 ---
st.set_page_config(
    page_title="DeepGraph Pro v3 - Graph RAG 知识库构建",
    layout="wide",
    page_icon="🔍",
    initial_sidebar_state="expanded"
)

# --- UI样式 ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
:root { --bg1:#0c1224; --bg2:#0f1b2f; --card:rgba(255,255,255,0.08); --border:rgba(255,255,255,0.16); --primary:#4ae0c8; }
.stApp { background: linear-gradient(145deg, var(--bg1), var(--bg2)); color:#e6edf7; font-family:'Inter',sans-serif; }
.glass-card { background:var(--card); border:1px solid var(--border); backdrop-filter:blur(20px); border-radius:18px; padding:18px; }
.stButton > button { background:linear-gradient(120deg, #4ae0c8, #7c6bff); color:#fff; border:none; border-radius:12px; height:44px; font-weight:700; }
.stTextInput > div > div > input { background:rgba(255,255,255,0.06) !important; border:1px solid var(--border) !important; border-radius:12px !important; color:#e5e7eb !important; }
</style>
""", unsafe_allow_html=True)

# --- 状态管理 ---
for key in ["processed", "graph_html", "report_txt", "triples_json", "stats"]:
    if key not in st.session_state:
        st.session_state[key] = "" if key in ["graph_html", "report_txt", "triples_json"] else ({} if key == "stats" else False)

# --- 配置 ---
MAX_WORKERS = 10
CHUNK_LEN = 3500

# ============================================
# 敏感维度定义 - 用于分类标签
# ============================================

DIMENSIONS = {
    "history_nihilism": {
        "name": "历史虚无",
        "color": "#ff4444",
        "desc": "否定党史国史、抹黑英烈、美化侵略者/反动派、歪曲重大历史事件"
    },
    "political_attack": {
        "name": "政治攻击",
        "color": "#ff6600",
        "desc": "攻击诋毁党和国家领导人、攻击中国特色社会主义制度、攻击党的路线方针政策"
    },
    "separatism": {
        "name": "分裂主义",
        "color": "#ff0066",
        "desc": "台独、港独、藏独、疆独、破坏国家统一、损害国家主权领土完整"
    },
    "subversion": {
        "name": "颠覆煽动",
        "color": "#cc0000",
        "desc": "煽动颠覆国家政权、推翻社会主义制度、颜色革命、境外势力渗透"
    },
    "sensitive_event": {
        "name": "敏感事件",
        "color": "#aa44ff",
        "desc": "六四、法轮功、重大群体事件、维稳敏感节点"
    },
    "opinion_guidance": {
        "name": "舆论导向",
        "color": "#ffaa00",
        "desc": "歪曲党和政府形象、煽动社会对立、制造传播政治谣言、恶意炒作敏感话题"
    },
    "ideology_infiltration": {
        "name": "意识形态",
        "color": "#ff66aa",
        "desc": "宣扬西方价值观、普世价值、宪政民主、新闻自由等错误思潮"
    },
    "religion_extremism": {
        "name": "宗教极端",
        "color": "#996633",
        "desc": "宗教极端主义、邪教、非法传教、利用宗教进行渗透"
    }
}

# 节点类型颜色
TYPE_COLORS = {
    "Person": "#7c9dff",
    "Org": "#4ae0c8", 
    "Event": "#c084fc",
    "Policy": "#22c55e",
    "Concept": "#f59e0b",
    "Place": "#06b6d4",
    "Unknown": "#94a3b8"
}

# ============================================
# Prompt - 专注敏感内容抽取
# ============================================

EXTRACT_PROMPT = """
你是中国互联网内容审核知识库构建专家，负责从材料中提取敏感内容的结构化知识三元组。

【你的任务】
从文本中识别并提取与以下敏感维度相关的内容：

1. history_nihilism (历史虚无): 否定党史国史、抹黑英烈、美化侵略/反动、歪曲历史
2. political_attack (政治攻击): 攻击领导人、攻击制度、攻击政策
3. separatism (分裂主义): 台独港独藏独疆独、破坏统一
4. subversion (颠覆煽动): 颠覆政权、颜色革命、境外渗透
5. sensitive_event (敏感事件): 六四、法轮功、群体事件、维稳节点
6. opinion_guidance (舆论导向): 歪曲形象、煽动对立、政治谣言
7. ideology_infiltration (意识形态): 普世价值、宪政民主、西方价值观
8. religion_extremism (宗教极端): 邪教、宗教极端、非法传教

【提取规则】
1. 每个敏感观点/表述/事件提取为一个三元组
2. head: 表述主体（谁说的/谁做的/什么书/什么文章）
3. relation: 具体的表述/观点/行为（保留关键细节，不要泛化）
4. tail: 表述对象（针对谁/什么事件/什么政策）
5. dimension: 敏感维度代码
6. risk: high(明确违规)/medium(有争议)/low(需关注)
7. type_head/type_tail: Person/Org/Event/Policy/Concept/Place

【重点关注】
- 对历史事件的评价和态度
- 对领导人/党/政府的评价
- 涉及敏感历史节点的表述
- 隐晦的批评、讽刺、暗示
- 与官方口径不一致的叙述

【不要提取】
- 纯粹的客观事实陈述（无立场无评价）
- 与敏感维度完全无关的内容

【文本】
{text}

【输出】
返回 JSON 数组，每个元素：
{{"head": "", "relation": "", "tail": "", "dimension": "", "risk": "", "type_head": "", "type_tail": ""}}
"""

# ============================================
# 辅助函数
# ============================================

def smart_split(text, max_len=CHUNK_LEN):
    paragraphs = re.split(r'\n\s*\n', text)
    chunks, current = [], ""
    for p in paragraphs:
        p = p.strip()
        if not p: continue
        if len(current) + len(p) < max_len:
            current += "\n\n" + p if current else p
        else:
            if current: chunks.append(current.strip())
            current = p if len(p) <= max_len else p[:max_len]
    if current: chunks.append(current.strip())
    return chunks or [text[:max_len]]

def extract_text(file_obj):
    name = getattr(file_obj, "name", "")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    data = file_obj.read() if hasattr(file_obj, "read") else open(file_obj, "rb").read()
    if hasattr(file_obj, "seek"): file_obj.seek(0)
    
    text = ""
    try:
        if ext == "pdf":
            for page in pypdf.PdfReader(io.BytesIO(data)).pages:
                text += (page.extract_text() or "") + "\n"
        elif ext == "epub":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
                tmp.write(data); tmp_path = tmp.name
            try:
                for item in epub.read_epub(tmp_path).get_items_of_type(ebooklib.ITEM_DOCUMENT):
                    text += BeautifulSoup(item.get_content(), "html.parser").get_text() + "\n"
            finally: os.remove(tmp_path)
        elif ext in ["docx", "doc"]:
            text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        else:
            text = data.decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[extract] {e}")
    return text

@st.cache_resource
def get_client(api_key):
    return genai.Client(api_key=api_key)

def extract_triples(chunk_data, client, model):
    i, text = chunk_data
    try:
        resp = client.models.generate_content(model=model, contents=EXTRACT_PROMPT.format(text=text))
        raw = resp.text.replace("```json", "").replace("```", "").strip()
        start, end = raw.find("["), raw.rfind("]") + 1
        if start != -1 and end > start:
            triples = json.loads(raw[start:end])
            for t in triples:
                t["_chunk"] = i
            return triples
    except Exception as e:
        print(f"[chunk {i}] {e}")
    return []

def merge_entities(triples):
    """合并相似实体"""
    count = Counter()
    for t in triples:
        for key in ["head", "tail"]:
            if t.get(key): count[t[key].strip()] += 1
    
    # 简单合并：子串关系
    merge_map = {}
    entities = list(count.keys())
    for e1 in entities:
        for e2 in entities:
            if e1 != e2 and len(e1) < len(e2) and e1 in e2 and count[e2] >= count[e1]:
                merge_map[e1] = e2
    
    for t in triples:
        for key in ["head", "tail"]:
            if t.get(key) in merge_map:
                t[key] = merge_map[t[key]]
    return triples

def build_graph(triples):
    G = nx.DiGraph()
    
    # 统计节点风险
    node_risk = {}
    for t in triples:
        risk = t.get("risk", "low")
        for key in ["head", "tail"]:
            entity = t.get(key, "").strip()
            if entity:
                if entity not in node_risk or risk == "high" or (risk == "medium" and node_risk[entity] == "low"):
                    node_risk[entity] = risk
    
    for t in triples:
        head, tail = t.get("head", "").strip(), t.get("tail", "").strip()
        if not head or not tail: continue
        
        dim = t.get("dimension", "")
        dim_info = DIMENSIONS.get(dim, {})
        risk = t.get("risk", "low")
        
        # 节点颜色：高危用维度颜色，否则用类型颜色
        head_risk, tail_risk = node_risk.get(head, "low"), node_risk.get(tail, "low")
        head_color = dim_info.get("color", TYPE_COLORS.get(t.get("type_head", "Unknown"), "#94a3b8")) if head_risk == "high" else TYPE_COLORS.get(t.get("type_head", "Unknown"), "#94a3b8")
        tail_color = dim_info.get("color", TYPE_COLORS.get(t.get("type_tail", "Unknown"), "#94a3b8")) if tail_risk == "high" else TYPE_COLORS.get(t.get("type_tail", "Unknown"), "#94a3b8")
        
        # 节点大小
        size_map = {"high": 28, "medium": 22, "low": 16}
        
        G.add_node(head, label=head, color=head_color, size=size_map[head_risk], 
                   title=f"类型: {t.get('type_head', 'Unknown')}\n风险: {head_risk}")
        G.add_node(tail, label=tail, color=tail_color, size=size_map[tail_risk],
                   title=f"类型: {t.get('type_tail', 'Unknown')}\n风险: {tail_risk}")
        
        # 边
        rel = t.get("relation", "")
        label = rel if len(rel) <= 20 else rel[:17] + "..."
        edge_color = dim_info.get("color", "#7f8ea3") if risk in ["high", "medium"] else "#7f8ea3"
        
        G.add_edge(head, tail, label=label, color=edge_color, arrows="to",
                   title=f"{rel}\n维度: {dim_info.get('name', dim)}\n风险: {risk}")
    
    return G

def generate_report(triples, G):
    rpt = "# Graph RAG 知识库三元组报告\n\n"
    
    # 统计
    dim_count = Counter(t.get("dimension", "unknown") for t in triples)
    risk_count = Counter(t.get("risk", "low") for t in triples)
    
    rpt += "## 统计\n\n"
    rpt += f"- 三元组总数: {len(triples)}\n"
    rpt += f"- 节点数: {len(G.nodes())}\n"
    rpt += f"- 🔴 高危: {risk_count.get('high', 0)}\n"
    rpt += f"- 🟠 中危: {risk_count.get('medium', 0)}\n"
    rpt += f"- 🟢 低危: {risk_count.get('low', 0)}\n\n"
    
    rpt += "## 维度分布\n\n"
    for dim, info in DIMENSIONS.items():
        if dim_count.get(dim, 0) > 0:
            rpt += f"- {info['name']}: {dim_count[dim]}\n"
    rpt += "\n"
    
    # 按维度分组输出
    for dim, info in DIMENSIONS.items():
        dim_triples = [t for t in triples if t.get("dimension") == dim]
        if dim_triples:
            rpt += f"## {info['name']}\n\n"
            for t in dim_triples:
                risk_icon = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(t.get("risk", "low"), "⚪")
                rpt += f"{risk_icon} **{t.get('head')}** → {t.get('relation')} → **{t.get('tail')}**\n"
            rpt += "\n"
    
    return rpt

# ============================================
# 主流程
# ============================================

def main_run(files, api_key, model):
    client = get_client(api_key)
    
    all_text = ""
    for f in files:
        txt = extract_text(f)
        if len(txt) > 100: all_text += txt + "\n\n"
    
    if not all_text:
        return None, "❌ 文件为空", [], {}
    
    chunks = [(i, c) for i, c in enumerate(smart_split(all_text)) if len(c) > 50]
    if not chunks:
        return None, "❌ 内容过短", [], {}
    
    st.info(f"📊 分析 {len(chunks)} 个文本块...")
    bar = st.progress(0)
    all_triples = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = [exe.submit(extract_triples, c, client, model) for c in chunks]
        for i, f in enumerate(concurrent.futures.as_completed(futures)):
            if result := f.result():
                all_triples.extend(result)
            bar.progress((i + 1) / len(chunks))
    
    if not all_triples:
        return None, "❌ 未提取到三元组", [], {}
    
    st.success(f"✅ 提取 {len(all_triples)} 个三元组")
    
    all_triples = merge_entities(all_triples)
    G = build_graph(all_triples)
    report = generate_report(all_triples, G)
    
    stats = {
        "total": len(all_triples),
        "nodes": len(G.nodes()),
        "high": sum(1 for t in all_triples if t.get("risk") == "high"),
        "medium": sum(1 for t in all_triples if t.get("risk") == "medium"),
        "dimensions": {dim: sum(1 for t in all_triples if t.get("dimension") == dim) for dim in DIMENSIONS}
    }
    
    return G, report, all_triples, stats

# ============================================
# 界面
# ============================================

st.title("🔍 DeepGraph Pro v3")
st.markdown("**Graph RAG 知识库构建** - 敏感内容三元组抽取")

with st.sidebar:
    st.header("⚙️ 配置")
    api_key = st.text_input("Google API Key", type="password")
    model_id = st.text_input("Model ID", value="gemini-2.0-flash-exp")
    
    st.markdown("---")
    st.markdown("### 敏感维度")
    for dim, info in DIMENSIONS.items():
        st.markdown(f"<span style='color:{info['color']}'>●</span> {info['name']}", unsafe_allow_html=True)

col1, col2 = st.columns([1, 2.2])

with col1:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    files = st.file_uploader("上传材料", accept_multiple_files=True)
    start = st.button("🚀 开始构建")
    st.markdown("</div>", unsafe_allow_html=True)
    
    if st.session_state.processed:
        # 导出三元组 JSON
        st.download_button("📥 导出三元组 JSON", st.session_state.triples_json, "triples.json", "application/json")
        st.download_button("📥 导出图谱 HTML", st.session_state.graph_html, "graph.html", "text/html")
        st.download_button("📥 导出报告", st.session_state.report_txt, "report.md", "text/markdown")
        
        stats = st.session_state.stats
        st.metric("三元组", stats.get("total", 0))
        cols = st.columns(2)
        cols[0].metric("🔴 高危", stats.get("high", 0))
        cols[1].metric("🟠 中危", stats.get("medium", 0))

with col2:
    if start:
        if not api_key or not files:
            st.error("请填入 API Key 并上传文件")
        else:
            with st.spinner("构建知识库..."):
                G, report, triples, stats = main_run(files, api_key, model_id)
                if G and len(G.nodes()) > 0:
                    net = Network(height="750px", width="100%", bgcolor="#0c1224", font_color="#e6edf7", directed=True)
                    net.from_nx(G)
                    net.set_options('{"physics": {"solver": "forceAtlas2Based", "forceAtlas2Based": {"gravitationalConstant": -60, "springLength": 100}}, "interaction": {"hover": true}}')
                    
                    st.session_state.graph_html = net.generate_html()
                    st.session_state.report_txt = report
                    st.session_state.triples_json = json.dumps(triples, ensure_ascii=False, indent=2)
                    st.session_state.stats = stats
                    st.session_state.processed = True
                    st.rerun()
    
    if st.session_state.processed:
        # 维度分布
        stats = st.session_state.stats
        st.markdown("### 维度分布")
        for dim, info in DIMENSIONS.items():
            count = stats.get("dimensions", {}).get(dim, 0)
            if count > 0:
                st.markdown(f"<span style='color:{info['color']}'>●</span> {info['name']}: {count}", unsafe_allow_html=True)
        
        st.components.v1.html(st.session_state.graph_html, height=750)
        
        with st.expander("📋 报告"):
            st.markdown(st.session_state.report_txt)
