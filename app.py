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

st.set_page_config(page_title="DeepGraph Pro v3", layout="wide", page_icon="🕸️")

st.markdown("""
<style>
.stApp { background: linear-gradient(145deg, #0c1224, #0f1b2f); color: #e6edf7; }
.stButton > button { background: linear-gradient(120deg, #4ae0c8, #7c6bff); color: #fff; border: none; border-radius: 12px; }
.entity-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; margin: 2px; font-size: 0.85em; }
.entity-person { background: #ff6b6b33; color: #ff6b6b; }
.entity-event { background: #f59e0b33; color: #f59e0b; }
.entity-org { background: #22c55e33; color: #22c55e; }
</style>
""", unsafe_allow_html=True)

# ============================================
# Session State
# ============================================
if "processed" not in st.session_state:
    st.session_state.processed = False
if "graph_html" not in st.session_state:
    st.session_state.graph_html = ""
if "report" not in st.session_state:
    st.session_state.report = ""
if "entities" not in st.session_state:
    st.session_state.entities = []
if "relations" not in st.session_state:
    st.session_state.relations = []

MAX_WORKERS = 6
CHUNK_SIZE = 3500

# ============================================
# Schema定义 - 时政历史专用
# ============================================

ENTITY_TYPES = {
    "Person": "政治人物、历史人物、领导人、革命者、学者",
    "Event": "政治事件、历史事件、运动、战争、会议",
    "Organization": "政党、政府机构、军队、国际组织",
    "Policy": "政策、法规、制度、方针",
    "Ideology": "思想、理论、主义、学说",
    "Location": "国家、地区、城市、重要地点",
    "Time": "具体时间点或时间段",
}

RELATION_TYPES = [
    # 人物关系
    "领导", "继任", "前任", "下属", "同事", "对立",
    # 事件关系  
    "发起", "参与", "主导", "反对", "支持", "镇压",
    # 因果关系
    "导致", "引发", "源于", "结束于",
    # 评价关系
    "批评", "赞扬", "定性为", "评价为",
    # 归属关系
    "属于", "隶属", "包含", "位于",
    # 时间关系
    "发生于", "开始于", "结束于", "持续",
]

# ============================================
# 阶段一：实体抽取 Prompt
# ============================================

ENTITY_PROMPT = """你是专业的时政历史文档分析专家。从文本中识别重要实体。

## 实体类型定义
- Person: 政治人物、历史人物、领导人
- Event: 政治事件、历史事件、运动、战争、会议
- Organization: 政党、政府机构、军队、国际组织
- Policy: 政策、法规、制度、方针
- Ideology: 思想、理论、主义、学说
- Location: 重要地点（非普通地名）
- Time: 关键时间点或时间段

## 抽取规则
1. 只抽取与时政历史相关的**重要**实体
2. 过滤日常生活、一般描述中的普通词汇
3. 人名需完整（如"毛泽东"而非"毛"）
4. 事件名称需规范（如"六四事件"而非"那件事"）

## 示例
文本："1978年12月，邓小平主持召开十一届三中全会，正式确立改革开放政策。"
输出：
```json
[
  {"name": "邓小平", "type": "Person"},
  {"name": "十一届三中全会", "type": "Event"},
  {"name": "改革开放", "type": "Policy"},
  {"name": "1978年12月", "type": "Time"}
]
```

## 待分析文本
{text}

## 输出
仅返回JSON数组，不要其他内容："""

# ============================================
# 阶段二：关系抽取 Prompt
# ============================================

RELATION_PROMPT = """你是专业的知识图谱构建专家。根据文本内容，在给定实体之间建立关系。

## 已识别的实体
{entities}

## 关系类型参考
{relation_types}

## 抽取规则
1. 只在上述实体之间建立关系
2. 关系必须有明确的方向（source → relation → target）
3. 关系描述要简洁（2-6个字）
4. 可以使用参考关系类型，也可以自定义更准确的描述
5. 每条关系可附带细节说明

## 示例
文本："邓小平主持召开十一届三中全会，确立了改革开放政策。"
实体：邓小平(Person), 十一届三中全会(Event), 改革开放(Policy)
输出：
```json
[
  {{"source": "邓小平", "relation": "主持召开", "target": "十一届三中全会", "detail": "1978年12月"}},
  {{"source": "十一届三中全会", "relation": "确立", "target": "改革开放", "detail": "经济体制改革"}}
]
```

## 待分析文本
{text}

## 输出
仅返回JSON数组："""

# ============================================
# 工具函数
# ============================================

def split_text(text, size=CHUNK_SIZE):
    """分块，保持段落完整性"""
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
    """读取各种格式的文件"""
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

def call_llm(client, model, prompt):
    """调用LLM并解析JSON"""
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        raw = resp.text.replace("```json", "").replace("```", "").strip()
        start, end = raw.find("["), raw.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception as e:
        print(f"LLM Error: {e}")
    return []

# ============================================
# 两阶段抽取
# ============================================

def extract_entities(chunk, client, model):
    """阶段一：抽取实体"""
    prompt = ENTITY_PROMPT.format(text=chunk)
    entities = call_llm(client, model, prompt)
    # 过滤无效实体
    valid = []
    for e in entities:
        name = e.get("name", "").strip()
        etype = e.get("type", "")
        if len(name) >= 2 and etype in ENTITY_TYPES:
            valid.append({"name": name, "type": etype})
    return valid

def extract_relations(chunk, entities, client, model):
    """阶段二：抽取关系"""
    if not entities:
        return []
    
    # 构建实体描述
    entity_desc = ", ".join([f"{e['name']}({e['type']})" for e in entities])
    relation_desc = ", ".join(RELATION_TYPES)
    
    prompt = RELATION_PROMPT.format(
        text=chunk,
        entities=entity_desc,
        relation_types=relation_desc
    )
    
    relations = call_llm(client, model, prompt)
    
    # 验证关系的source和target都在实体列表中
    entity_names = {e["name"] for e in entities}
    valid = []
    for r in relations:
        src = r.get("source", "").strip()
        tgt = r.get("target", "").strip()
        rel = r.get("relation", "").strip()
        if src and tgt and rel and src in entity_names and tgt in entity_names:
            valid.append({
                "source": src,
                "relation": rel,
                "target": tgt,
                "detail": r.get("detail", "")
            })
    return valid

def deduplicate_entities(all_entities):
    """实体去重"""
    seen = {}
    for e in all_entities:
        name = e["name"]
        if name not in seen:
            seen[name] = e
    return list(seen.values())

def deduplicate_relations(all_relations):
    """关系去重"""
    seen = set()
    unique = []
    for r in all_relations:
        key = f"{r['source']}|{r['relation']}|{r['target']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique

# ============================================
# 图谱构建
# ============================================

def build_graph(entities, relations):
    """构建有向图"""
    G = nx.DiGraph()
    
    # 实体类型颜色
    type_colors = {
        "Person": "#ff6b6b",
        "Event": "#f59e0b",
        "Organization": "#22c55e",
        "Policy": "#06b6d4",
        "Ideology": "#c084fc",
        "Location": "#7c9dff",
        "Time": "#94a3b8",
    }
    
    # 统计实体出现次数（用于节点大小）
    entity_degree = Counter()
    for r in relations:
        entity_degree[r["source"]] += 1
        entity_degree[r["target"]] += 1
    
    max_degree = max(entity_degree.values()) if entity_degree else 1
    
    # 添加节点
    entity_map = {e["name"]: e for e in entities}
    for name, e in entity_map.items():
        degree = entity_degree.get(name, 0)
        size = 15 + (degree / max_degree) * 40  # 15-55
        color = type_colors.get(e["type"], "#94a3b8")
        
        G.add_node(name, 
                   label=name, 
                   color=color, 
                   size=size,
                   title=f"{name}\n类型: {e['type']}\n关联数: {degree}")
    
    # 添加边
    for r in relations:
        src, tgt = r["source"], r["target"]
        if not G.has_node(src):
            G.add_node(src, label=src, color="#94a3b8", size=15)
        if not G.has_node(tgt):
            G.add_node(tgt, label=tgt, color="#94a3b8", size=15)
        
        # 边标签
        label = r["relation"]
        title = f"{src} → {r['relation']} → {tgt}"
        if r.get("detail"):
            title += f"\n{r['detail']}"
        
        G.add_edge(src, tgt, 
                   label=label,
                   title=title,
                   arrows="to",
                   color="#4ae0c8aa")
    
    return G

# ============================================
# 主流程
# ============================================

def run(files, api_key, model, progress_callback=None):
    client = get_client(api_key)
    
    # 读取所有文件
    all_text = ""
    for f in files:
        all_text += read_file(f) + "\n\n"
    
    if len(all_text.strip()) < 100:
        return None, None, "文件内容过少"
    
    # 分块
    chunks = split_text(all_text)
    total_steps = len(chunks) * 2  # 两阶段
    current_step = 0
    
    st.info(f"📄 共 {len(chunks)} 个文本块，开始两阶段抽取...")
    
    # 阶段一：实体抽取
    st.write("**阶段一：实体识别**")
    bar1 = st.progress(0, text="抽取实体中...")
    all_entities = []
    
    for i, chunk in enumerate(chunks):
        entities = extract_entities(chunk, client, model)
        all_entities.extend(entities)
        current_step += 1
        bar1.progress(current_step / total_steps, text=f"实体抽取 {i+1}/{len(chunks)}")
    
    # 实体去重
    all_entities = deduplicate_entities(all_entities)
    st.success(f"✅ 识别到 {len(all_entities)} 个唯一实体")
    
    # 阶段二：关系抽取
    st.write("**阶段二：关系抽取**")
    bar2 = st.progress(0, text="抽取关系中...")
    all_relations = []
    
    for i, chunk in enumerate(chunks):
        # 只用这个chunk相关的实体
        relations = extract_relations(chunk, all_entities, client, model)
        all_relations.extend(relations)
        current_step += 1
        bar2.progress(current_step / total_steps, text=f"关系抽取 {i+1}/{len(chunks)}")
    
    # 关系去重
    all_relations = deduplicate_relations(all_relations)
    st.success(f"✅ 抽取到 {len(all_relations)} 条唯一关系")
    
    if not all_relations:
        return None, None, "未抽取到有效关系"
    
    # 构建图谱
    G = build_graph(all_entities, all_relations)
    
    # 生成报告
    report = generate_report(all_entities, all_relations)
    
    return G, (all_entities, all_relations), report

def generate_report(entities, relations):
    """生成分析报告"""
    report = "# 知识图谱抽取报告\n\n"
    report += f"## 📊 统计\n"
    report += f"- 实体数量: {len(entities)}\n"
    report += f"- 关系数量: {len(relations)}\n\n"
    
    # 按类型分组实体
    report += "## 🏷️ 实体列表\n\n"
    by_type = {}
    for e in entities:
        t = e["type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(e["name"])
    
    for t, names in by_type.items():
        report += f"### {t} ({len(names)})\n"
        report += ", ".join(names) + "\n\n"
    
    # 关系列表
    report += "## 🔗 关系列表\n\n"
    for r in relations:
        detail = f" *({r['detail']})*" if r.get("detail") else ""
        report += f"- {r['source']} → **{r['relation']}** → {r['target']}{detail}\n"
    
    return report

# ============================================
# 界面
# ============================================

st.title("🕸️ DeepGraph Pro v3")
st.caption("两阶段知识图谱抽取 | 时政历史专用")

with st.sidebar:
    st.subheader("⚙️ 配置")
    api_key = st.text_input("API Key", type="password")
    model = st.text_input("Model", value="gemini-2.0-flash-exp")
    
    st.divider()
    st.subheader("📋 Schema")
    with st.expander("实体类型"):
        for t, desc in ENTITY_TYPES.items():
            st.write(f"**{t}**: {desc}")
    with st.expander("关系类型"):
        st.write(", ".join(RELATION_TYPES))

# 主界面使用tabs
tab1, tab2, tab3 = st.tabs(["📤 上传", "🕸️ 图谱", "📊 报告"])

with tab1:
    files = st.file_uploader("上传文档", accept_multiple_files=True, 
                             type=["pdf", "epub", "docx", "txt"])
    
    if st.button("🚀 开始抽取", type="primary", use_container_width=True):
        if api_key and files:
            with st.container():
                G, data, report = run(files, api_key, model)
                
                if G and data:
                    entities, relations = data
                    
                    # 生成可视化
                    net = Network(height="700px", width="100%", 
                                  bgcolor="#0c1224", font_color="#e6edf7", 
                                  directed=True)
                    net.from_nx(G)
                    net.set_options('''
{
  "physics": {
    "enabled": true,
    "solver": "forceAtlas2Based",
    "forceAtlas2Based": {
      "gravitationalConstant": -80,
      "centralGravity": 0.015,
      "springLength": 120,
      "springConstant": 0.08,
      "damping": 0.85,
      "avoidOverlap": 0.95
    },
    "stabilization": {"enabled": true, "iterations": 300}
  },
  "edges": {
    "smooth": {"type": "continuous"},
    "font": {"size": 11, "color": "#94a3b8", "strokeWidth": 0}
  },
  "interaction": {"hover": true, "navigationButtons": true, "keyboard": true}
}
                    ''')
                    
                    st.session_state.graph_html = net.generate_html()
                    st.session_state.report = report
                    st.session_state.entities = entities
                    st.session_state.relations = relations
                    st.session_state.processed = True
                    st.rerun()
                else:
                    st.error(report)
        else:
            st.warning("请填写API Key并上传文件")

with tab2:
    if st.session_state.processed:
        # 统计信息
        col1, col2, col3 = st.columns(3)
        col1.metric("实体", len(st.session_state.entities))
        col2.metric("关系", len(st.session_state.relations))
        col3.metric("节点连接", 
                    sum(1 for _ in st.session_state.relations))
        
        # 图谱
        st.components.v1.html(st.session_state.graph_html, height=700)
    else:
        st.info("请先上传文档并抽取")

with tab3:
    if st.session_state.processed:
        # 下载按钮
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📥 下载实体+关系 JSON",
                json.dumps({
                    "entities": st.session_state.entities,
                    "relations": st.session_state.relations
                }, ensure_ascii=False, indent=2),
                "knowledge_graph.json",
                use_container_width=True
            )
        with col2:
            st.download_button(
                "📥 下载报告 Markdown",
                st.session_state.report,
                "report.md",
                use_container_width=True
            )
        
        st.divider()
        st.markdown(st.session_state.report)
    else:
        st.info("请先上传文档并抽取")
