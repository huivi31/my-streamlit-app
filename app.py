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
    page_icon="☁️",
    initial_sidebar_state="expanded"
)

# --- 2. 样式优化 (Glassmorphism Theme) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    .stApp { 
        background: linear-gradient(135deg, #667eea 0%, #764ba2 25%, #f093fb 50%, #4facfe 75%, #00f2fe 100%);
        background-size: 400% 400%;
        animation: gradientShift 15s ease infinite;
        color: #ffffff;
    }
    
    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    .glass-card {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 12px;
        height: 48px;
        font-weight: 600;
        font-size: 16px;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px 0 rgba(102, 126, 234, 0.4);
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
        box-shadow: 0 6px 20px 0 rgba(102, 126, 234, 0.6);
        transform: translateY(-2px);
    }
    
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        background: rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.3);
        border-radius: 10px;
        color: #ffffff;
        padding: 12px;
    }
    
    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder {
        color: rgba(255, 255, 255, 0.6);
    }
    
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
        border-radius: 10px;
    }
    
    h1, h2, h3 {
        color: #ffffff;
        text-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
    }
    
    .stSidebar {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
    }
    
    .stDownloadButton > button {
        background: rgba(255, 255, 255, 0.2);
        backdrop-filter: blur(10px);
        color: white;
        border: 1px solid rgba(255, 255, 255, 0.3);
        border-radius: 10px;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    .stDownloadButton > button:hover {
        background: rgba(255, 255, 255, 0.3);
        transform: translateY(-1px);
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 状态管理 ---
if 'processed' not in st.session_state: st.session_state.processed = False
if 'graph_html' not in st.session_state: st.session_state.graph_html = ""
if 'report_txt' not in st.session_state: st.session_state.report_txt = ""
if 'summary' not in st.session_state: st.session_state.summary = ""

# --- 4. 缓存的 GenAI 客户端 ---
@st.cache_resource
def get_genai_client(api_key):
    """Reusable cached Google GenAI client"""
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"Failed to create GenAI client: {e}")
        return None

# --- 5. 核心功能 ---
# Alias normalization map
ALIAS_MAP = {
    "邓小平": ["小平", "邓"],
    "毛泽东": ["毛主席", "毛"],
    "习近平": ["习", "近平", "习主席"],
}

def normalize_entity(entity):
    """Normalize entity names using alias map with weak matching"""
    if not entity or not isinstance(entity, str):
        return entity
    entity_stripped = entity.strip()
    
    # Direct match in alias map
    for canonical, aliases in ALIAS_MAP.items():
        if entity_stripped == canonical:
            return canonical
        if entity_stripped in aliases:
            return canonical
    
    # Weak matching - check if entity contains canonical or alias
    for canonical, aliases in ALIAS_MAP.items():
        if canonical in entity_stripped or entity_stripped in canonical:
            return canonical
        for alias in aliases:
            if alias in entity_stripped or entity_stripped in alias:
                return canonical
    
    return entity_stripped

def is_banal_predicate(predicate):
    """Filter out empty or banal predicates"""
    if not predicate or not isinstance(predicate, str):
        return True
    
    predicate_lower = predicate.strip().lower()
    
    # Empty or too short
    if len(predicate_lower) < 2:
        return True
    
    # Common banal predicates to filter
    banal_list = [
        "是", "有", "在", "为", "的", "了", "和", "与",
        "is", "are", "was", "were", "has", "have", "had",
        "be", "been", "being"
    ]
    
    return predicate_lower in banal_list

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
    i, text, client, model = chunk_data
    
    # Improved prompt with direction enforcement and type constraints
    prompt = f"""
【任务】从文本中提取精确的主谓宾(SVO)三元组以构建知识图谱。

【关键要求】
1. **方向性(Direction)**: 明确区分主动和被动关系
   - 主动关系: Head是动作的发起者 (例: "张三批评李四")
   - 被动关系: Head是动作的承受者 (例: "李四被张三批评")
   - 在relation字段中标明: 主动动词(如"批评"、"领导"、"攻击") 或 被动标记(如"被批评"、"被领导"、"受到攻击")

2. **动词具体性**: 保持动词的原始具体含义，不要过度泛化
   - ✓ 正确: "指挥"、"策划"、"执行"、"资助"
   - ✗ 错误: "相关"、"涉及"、"有关"、"参与" (太泛化)

3. **类型分类(Type)**: 为每个实体标注类型
   - [HighRisk]: 高风险实体(武器、暴力、犯罪组织)
   - [Faction]: 政治派系、组织、团体
   - [Person]: 个人、领导人
   - [Outcome]: 结果、后果、事件
   - [NoRisk]: 普通实体

4. **完整性**: 每个三元组必须包含head、type_head、relation、tail、type_tail、direction字段

【输出格式】JSON数组:
[
  {{
    "head": "实体1名称",
    "type_head": "类型",
    "relation": "具体动词",
    "tail": "实体2名称",
    "type_tail": "类型",
    "direction": "active"或"passive"
  }}
]

【文本内容】
{text[:8000]}

请严格按照JSON格式输出，确保每个三元组都包含所有必需字段。
"""
    
    try:
        # Rate limiting
        time.sleep(0.5)
        response = client.models.generate_content(model=model, contents=prompt)
        raw = response.text.replace("```json", "").replace("```", "").strip()
        s, e = raw.find('['), raw.rfind(']') + 1
        if s == -1 or e == 0:
            return []
        
        result = json.loads(raw[s:e])
        return result if isinstance(result, list) else []
    except json.JSONDecodeError as e:
        print(f"JSON parse error in chunk {i}: {e}")
        return []
    except Exception as e:
        print(f"Error in chunk {i}: {e}")
        return []

def trim_graph_nodes(raw_triples, min_nodes=50, max_nodes=300):
    """Trim nodes based on frequency to stay within bounds"""
    if not raw_triples:
        return raw_triples, False
    
    # Count node frequencies
    node_freq = Counter()
    for item in raw_triples:
        h, t = item.get('head'), item.get('tail')
        if h:
            node_freq[h] += 1
        if t:
            node_freq[t] += 1
    
    unique_nodes = len(node_freq)
    
    # If within bounds, no trimming needed
    if min_nodes <= unique_nodes <= max_nodes:
        return raw_triples, False
    
    # If less than min_nodes, skip trimming
    if unique_nodes < min_nodes:
        return raw_triples, False
    
    # If more than max_nodes, keep only top frequent nodes
    if unique_nodes > max_nodes:
        top_nodes = set([node for node, _ in node_freq.most_common(max_nodes)])
        trimmed = [
            item for item in raw_triples
            if item.get('head') in top_nodes and item.get('tail') in top_nodes
        ]
        return trimmed, True
    
    return raw_triples, False

def truncate_label(label, max_length=30):
    """Truncate long labels for visualization"""
    if not label or not isinstance(label, str):
        return label
    if len(label) <= max_length:
        return label
    return label[:max_length-3] + "..."

def main_run(files, api_key, model):
    # Get cached client
    client = get_genai_client(api_key)
    if not client:
        return None, "❌ 无法创建 GenAI 客户端", ""
    
    # Extract and chunk documents with overlap
    chunks = []
    chunk_size = 12000  # ~12k characters
    overlap = 800  # 800 character overlap
    
    for f in files:
        txt = extract_text(f)
        if len(txt) > 100:
            # Create overlapping chunks
            start = 0
            while start < len(txt):
                end = start + chunk_size
                chunk = txt[start:end]
                if chunk:
                    chunks.append((len(chunks), chunk, client, model))
                start += chunk_size - overlap
                if end >= len(txt):
                    break
    
    if not chunks:
        return None, "❌ 文件内容为空或读取失败", ""

    st.info(f"🚀 云端引擎启动：分析 {len(chunks)} 个片段 (每片段 ~{chunk_size} 字符，重叠 {overlap} 字符)...")
    bar = st.progress(0)
    raw = []
    
    # Cap concurrency based on chunk count (<=4)
    max_workers = min(4, max(1, len(chunks)))
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = [exe.submit(analyze_svo, c) for c in chunks]
        for i, f in enumerate(concurrent.futures.as_completed(futures)):
            if res := f.result():
                raw.extend(res)
            bar.progress((i+1)/len(chunks))

    if not raw:
        return None, "❌ 未提取到数据，请检查 API Key 或模型权限", ""

    # Apply alias normalization and filter banal predicates
    normalized_triples = []
    for item in raw:
        h = normalize_entity(item.get('head'))
        t = normalize_entity(item.get('tail'))
        r = item.get('relation')
        
        # Filter banal predicates
        if is_banal_predicate(r):
            continue
        
        if h and t and r:
            normalized_triples.append({
                'head': h,
                'tail': t,
                'relation': r,
                'type_head': item.get('type_head', 'Person'),
                'type_tail': item.get('type_tail', 'Person'),
                'direction': item.get('direction', 'active')
            })
    
    # Trim nodes if necessary
    trimmed_triples, was_trimmed = trim_graph_nodes(normalized_triples, min_nodes=50, max_nodes=300)
    
    if was_trimmed:
        st.warning(f"⚠️ 节点数超过300，已自动裁剪至前300个最频繁节点")
    
    # Build graph
    G = nx.DiGraph()
    COLORS = {
        "HighRisk": "#dc3545",
        "Person": "#0d6efd",
        "Outcome": "#6c757d",
        "Faction": "#6f42c1",
        "NoRisk": "#198754"
    }
    
    for item in trimmed_triples:
        h, t, r = item['head'], item['tail'], item['relation']
        ht, tt = item['type_head'], item['type_tail']
        direction = item.get('direction', 'active')
        
        # Add nodes with colors
        G.add_node(h, label=h, color=COLORS.get(ht, "#0d6efd"), size=20, title=f"{h} ({ht})")
        G.add_node(t, label=t, color=COLORS.get(tt, "#0d6efd"), size=20, title=f"{t} ({tt})")
        
        # Add edge with direction styling
        edge_style = "solid" if direction == "active" else "dashed"
        edge_label = truncate_label(r, max_length=30)
        
        G.add_edge(h, t, label=edge_label, color="#adb5bd", 
                   title=r, dashes=(direction == "passive"))

    # Generate summary
    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()
    
    # Count types
    type_counts = {"HighRisk": 0, "Person": 0, "Outcome": 0, "Faction": 0, "NoRisk": 0}
    for item in trimmed_triples:
        type_counts[item['type_head']] = type_counts.get(item['type_head'], 0) + 1
        type_counts[item['type_tail']] = type_counts.get(item['type_tail'], 0) + 1
    
    # Determine status message
    status_msg = "已自动裁剪至前300个高频节点" if was_trimmed else "无需裁剪"
    
    summary = f"""# DeepGraph Report Summary

## 统计信息
- **节点数 (Nodes)**: {node_count}
- **边数 (Edges)**: {edge_count}
- **总三元组 (Total Triples)**: {len(trimmed_triples)}

## 类型分布 (Type Distribution)
- **HighRisk**: {type_counts.get('HighRisk', 0)}
- **Person**: {type_counts.get('Person', 0)}
- **Faction**: {type_counts.get('Faction', 0)}
- **Outcome**: {type_counts.get('Outcome', 0)}
- **NoRisk**: {type_counts.get('NoRisk', 0)}

## 图谱信息
- **边样式**: 实线=主动关系, 虚线=被动关系
- **状态**: {status_msg}

---

"""
    
    # Generate triples listing
    rpt = summary + "## 关系三元组 (Relationship Triples)\n\n"
    for item in trimmed_triples:
        direction_arrow = "-->" if item['direction'] == "active" else "~~>"
        rpt += f"{item['head']} {direction_arrow}[{item['relation']}]{direction_arrow} {item['tail']}\n"
        
    return G, rpt, summary

# --- 6. 界面 ---
st.title("DeepGraph Pro (Cloud Edition)")

with st.sidebar:
    st.header("Settings")
    st.success("✅ 云端环境已就绪")
    
    api_key = st.text_input("Google API Key", type="password")
    # 默认使用最稳的 2.0 Flash
    model_id = st.text_input("Model ID", value="gemini-2.0-flash-exp")
    
    if st.button("🔍 Check Available Models"):
        if not api_key:
            st.error("Please enter API Key first")
        else:
            try:
                client = get_genai_client(api_key)
                if client:
                    # 修复：新版 SDK 迭代器写法
                    models = [m.name for m in client.models.list() if "gemini" in m.name]
                    st.write(models)
            except Exception as e:
                st.error(f"Error: {e}")

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    # 修复：去掉了 label 参数，只留提示词
    files = st.file_uploader("Upload Files (PDF/DOCX/TXT)", accept_multiple_files=True)
    st.markdown("<br>", unsafe_allow_html=True)
    start = st.button("🚀 Start Analysis")
    st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state.processed:
        st.download_button("Download Graph HTML", st.session_state.graph_html, "graph.html", "text/html")
        st.download_button("Download Report TXT", st.session_state.report_txt, "report.txt", "text/plain")
        
        # Display summary in sidebar
        if st.session_state.summary:
            st.markdown("---")
            st.markdown(st.session_state.summary)

with col2:
    if start:
        if not api_key or not files:
            st.error("请填入 API Key 并上传文件")
        else:
            with st.spinner("Analyzing on Cloud..."):
                G, rpt, summary = main_run(files, api_key, model_id)
                if G:
                    net = Network(height="700px", width="100%", bgcolor="#ffffff", font_color="#333", directed=True)
                    net.from_nx(G)
                    
                    # Configure physics for better visualization
                    net.set_options("""
                    {
                        "physics": {
                            "enabled": true,
                            "barnesHut": {
                                "gravitationalConstant": -8000,
                                "springLength": 200,
                                "springConstant": 0.04
                            }
                        },
                        "edges": {
                            "smooth": {
                                "enabled": true,
                                "type": "dynamic"
                            },
                            "arrows": {
                                "to": {
                                    "enabled": true,
                                    "scaleFactor": 0.5
                                }
                            }
                        }
                    }
                    """)
                    
                    st.session_state.graph_html = net.generate_html()
                    st.session_state.report_txt = rpt
                    st.session_state.summary = summary
                    st.session_state.processed = True
                    st.rerun()
                elif rpt:
                    st.error(rpt)

    if st.session_state.processed:
        st.components.v1.html(st.session_state.graph_html, height=700)
