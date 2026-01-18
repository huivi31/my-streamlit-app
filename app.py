import streamlit as st
import os, json, concurrent.futures, io, tempfile, re
from collections import Counter
import pypdf
from docx import Document
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from google import genai
from pyvis.network import Network
import networkx as nx

try:
    import community as community_louvain
    HAS_LOUVAIN = True
except:
    HAS_LOUVAIN = False

st.set_page_config(page_title="DeepGraph Pro", layout="wide", page_icon="�️")

st.markdown("""
<style>
.stApp { background: linear-gradient(145deg, #0c1224, #0f1b2f); color: #e6edf7; }
.stButton > button { background: linear-gradient(120deg, #4ae0c8, #7c6bff); color: #fff; border: none; border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

if "processed" not in st.session_state:
    st.session_state.processed = False
if "graph_html" not in st.session_state:
    st.session_state.graph_html = ""
if "report" not in st.session_state:
    st.session_state.report = ""
if "triples" not in st.session_state:
    st.session_state.triples = []

MAX_WORKERS = 8
CHUNK_SIZE = 4000

# ============================================
# Prompt - 核心逻辑
# ============================================

PROMPT = """
你是时政历史文档分析专家，负责从文本中提取结构化知识三元组，用于构建内容审核知识库。

【你的任务】
从文本中识别并提取所有与时政、历史、政治相关的信息，构建知识图谱。

【必须提取的内容类型】
1. 人物关系：谁和谁是什么关系、谁对谁做了什么
2. 事件描述：什么事件、谁参与、什么时间、什么结果
3. 观点立场：谁持有什么观点、对什么事件/人物的评价
4. 政策制度：什么政策、谁制定、影响什么
5. 组织关系：组织架构、隶属关系、对立关系
6. 历史评价：对历史事件/人物的定性、评价、争议

【不要提取】
- 日常生活琐事（吃饭睡觉、天气描写、风景描写）
- 与时政历史完全无关的内容

【分类标签 dimension】
- history: 历史事件、历史人物、历史评价、历史定性
- politics: 政治人物、政治事件、政策制度、权力关系
- ideology: 思想观点、意识形态、价值取向、理论主张
- sensitive: 敏感话题、争议内容、禁忌表述、红线内容
- military: 军事行动、军事人物、国防政策
- diplomacy: 外交关系、国际事件、领土争议
- economy_policy: 经济政策、经济改革、产业政策
- society: 社会事件、群体事件、社会运动、民生政策

【输出要求】
每个三元组必须包含:
- head: 主体（具体的人名/组织名/书名/概念，不要用代词）
- relation: 关系描述（具体的动作/观点/评价，保留原文关键词）
- tail: 客体（具体名称）
- dimension: 上述分类标签之一
- detail: 补充细节（时间/地点/背景/来源，如有）

【特别注意】
- 人名要用全名，不要用"他""她"等代词
- relation要具体，不要用"相关""有关"等模糊词
- 尽可能多地提取，每个重要信息点都要有三元组
- 敏感内容尤其要完整提取，不要遗漏

【待分析文本】
{text}

【输出】
返回JSON数组。尽可能完整提取，有多少信息就输出多少三元组。
"""


# ============================================
# 工具函数
# ============================================

def split_text(text, size=CHUNK_SIZE):
    paragraphs = re.split(r'\n\s*\n', text)
    chunks, current = [], ""
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(current) + len(p) < size:
            current += "\n\n" + p if current else p
        else:
            if current:
                chunks.append(current)
            current = p
    if current:
        chunks.append(current)
    return chunks or [text[:size]]

def read_file(f):
    name = getattr(f, "name", "")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    data = f.read()
    if hasattr(f, "seek"):
        f.seek(0)
    
    text = ""
    try:
        if ext == "pdf":
            for page in pypdf.PdfReader(io.BytesIO(data)).pages:
                text += (page.extract_text() or "") + "\n"
        elif ext == "epub":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
                tmp.write(data)
                path = tmp.name
            try:
                book = epub.read_epub(path)
                for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                    text += BeautifulSoup(item.get_content(), "html.parser").get_text() + "\n"
            finally:
                os.remove(path)
        elif ext in ["docx", "doc"]:
            text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        else:
            text = data.decode("utf-8", errors="ignore")
    except Exception as e:
        st.error(f"读取失败: {e}")
    return text

@st.cache_resource
def get_client(key):
    return genai.Client(api_key=key)

def extract(chunk, client, model):
    try:
        resp = client.models.generate_content(model=model, contents=PROMPT.format(text=chunk))
        raw = resp.text.replace("```json", "").replace("```", "").strip()
        start, end = raw.find("["), raw.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception as e:
        print(f"Error: {e}")
    return []

def merge_similar(triples):
    """合并相似实体"""
    entities = Counter()
    for t in triples:
        for k in ["head", "tail"]:
            if t.get(k):
                entities[t[k].strip()] += 1
    
    merge_map = {}
    names = list(entities.keys())
    for a in names:
        for b in names:
            if a != b and len(a) < len(b) and a in b:
                merge_map[a] = b
    
    for t in triples:
        for k in ["head", "tail"]:
            if t.get(k) in merge_map:
                t[k] = merge_map[t[k]]
    return triples

def build_graph(triples):
    G = nx.DiGraph()
    
    dim_colors = {
        "history": "#c084fc",
        "politics": "#ff6b6b",
        "ideology": "#f59e0b",
        "sensitive": "#ff4444",
        "military": "#22c55e",
        "diplomacy": "#06b6d4",
        "economy_policy": "#4ae0c8",
        "society": "#7c9dff",
    }
    
    for t in triples:
        h, r, tl = t.get("head", "").strip(), t.get("relation", ""), t.get("tail", "").strip()
        if not h or not tl:
            continue
        
        dim = t.get("dimension", "")
        color = dim_colors.get(dim, "#94a3b8")
        detail = t.get("detail", "")
        
        G.add_node(h, label=h, color=color, size=20)
        G.add_node(tl, label=tl, color=color, size=20)
        
        label = r if len(r) <= 20 else r[:18] + ".."
        title = r
        if detail:
            title += f"\n{detail}"
        
        G.add_edge(h, tl, label=label, color=color, arrows="to", title=title)
    
    return G

# ============================================
# 主流程
# ============================================

def run(files, api_key, model):
    client = get_client(api_key)
    
    # 读取所有文件
    all_text = ""
    for f in files:
        all_text += read_file(f) + "\n\n"
    
    if len(all_text.strip()) < 100:
        return None, "文件内容过少", []
    
    # 分块
    chunks = split_text(all_text)
    st.info(f"共 {len(chunks)} 个文本块")
    
    # 并行抽取
    bar = st.progress(0)
    all_triples = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = {exe.submit(extract, c, client, model): i for i, c in enumerate(chunks)}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                all_triples.extend(result)
            done += 1
            bar.progress(done / len(chunks))
    
    if not all_triples:
        return None, "未抽取到内容", []
    
    # 合并相似实体
    all_triples = merge_similar(all_triples)
    
    # 构建图谱
    G = build_graph(all_triples)
    
    # 生成报告
    report = f"# 抽取报告\n\n"
    report += f"- 三元组数量: {len(all_triples)}\n"
    report += f"- 节点数量: {len(G.nodes())}\n\n"
    
    # 按维度分组
    by_dim = {}
    for t in all_triples:
        dim = t.get("dimension", "other")
        if dim not in by_dim:
            by_dim[dim] = []
        by_dim[dim].append(t)
    
    for dim, items in by_dim.items():
        report += f"## {dim} ({len(items)})\n\n"
        for t in items:
            detail = f" [{t.get('detail')}]" if t.get("detail") else ""
            report += f"- {t.get('head')} → {t.get('relation')} → {t.get('tail')}{detail}\n"
        report += "\n"
    
    return G, report, all_triples

# ============================================
# 界面
# ============================================

st.title("�️ DeepGraph Pro")
st.caption("时政历史知识图谱构建")

with st.sidebar:
    api_key = st.text_input("API Key", type="password")
    model = st.text_input("Model", value="gemini-2.0-flash-exp")

col1, col2 = st.columns([1, 3])

with col1:
    files = st.file_uploader("上传文件", accept_multiple_files=True)
    if st.button("开始抽取"):
        if api_key and files:
            with st.spinner("处理中..."):
                G, report, triples = run(files, api_key, model)
                if G:
                    net = Network(height="750px", width="100%", bgcolor="#0c1224", font_color="#e6edf7", directed=True)
                    net.from_nx(G)
                    net.set_options('''
{
  "physics": {
    "enabled": true,
    "solver": "forceAtlas2Based",
    "forceAtlas2Based": {
      "gravitationalConstant": -100,
      "centralGravity": 0.01,
      "springLength": 150,
      "springConstant": 0.05,
      "damping": 0.8,
      "avoidOverlap": 0.9
    },
    "stabilization": {"enabled": true, "iterations": 500}
  },
  "edges": {"smooth": {"type": "continuous"}},
  "interaction": {"hover": true, "navigationButtons": true, "keyboard": true}
}
                    ''')
                    st.session_state.graph_html = net.generate_html()
                    st.session_state.report = report
                    st.session_state.triples = triples
                    st.session_state.processed = True
                    st.rerun()
                else:
                    st.error(report)
        else:
            st.warning("请填写API Key并上传文件")
    
    if st.session_state.processed:
        st.metric("三元组", len(st.session_state.triples))
        st.download_button("下载JSON", json.dumps(st.session_state.triples, ensure_ascii=False, indent=2), "triples.json")
        st.download_button("下载报告", st.session_state.report, "report.md")

with col2:
    if st.session_state.processed:
        st.components.v1.html(st.session_state.graph_html, height=700)


