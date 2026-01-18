import streamlit as st
import os, json, time, concurrent.futures, io, tempfile, re
from collections import Counter, defaultdict
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
    page_title="DeepGraph Pro v3 - 敏感内容分析",
    layout="wide",
    page_icon="🔍",
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
  --danger:#ff4444; --warning:#ffaa00; --safe:#44bb44;
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
.risk-high { background:rgba(255,68,68,0.2); border-left:4px solid #ff4444; padding:10px; margin:5px 0; border-radius:8px; }
.risk-medium { background:rgba(255,170,0,0.2); border-left:4px solid #ffaa00; padding:10px; margin:5px 0; border-radius:8px; }
.risk-low { background:rgba(68,187,68,0.2); border-left:4px solid #44bb44; padding:10px; margin:5px 0; border-radius:8px; }
.dimension-badge {
  display:inline-block; padding:4px 10px; border-radius:999px; font-weight:600; font-size:0.75em; margin:2px;
}
.dim-history { background:rgba(255,68,68,0.3); color:#ff6666; }
.dim-political { background:rgba(255,170,0,0.3); color:#ffcc00; }
.dim-sentiment { background:rgba(255,255,68,0.3); color:#ffff66; }
.dim-event { background:rgba(170,68,255,0.3); color:#cc99ff; }
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
if "sensitive_points" not in st.session_state:
    st.session_state.sensitive_points = []

# --- 参数配置 ---
MAX_WORKERS = 6
CHUNK_LEN = 2500  # 减小块大小以保留更多上下文

# ============================================
# 敏感维度定义
# ============================================

SENSITIVE_DIMENSIONS = {
    "history_nihilism": {
        "name": "历史虚无",
        "color": "#ff4444",
        "keywords": ["否定", "抹黑", "污蔑", "歪曲历史", "历史虚无", "英烈", "烈士", "革命", "抗日", "解放", "建党", "建国",
                    "文革", "大跃进", "反右", "土改", "三年困难", "饥荒", "死亡人数", "真相"],
        "desc": "否定党史、抹黑英烈、美化反面人物、歪曲重大历史事件"
    },
    "political_stance": {
        "name": "政治立场",
        "color": "#ffaa00",
        "keywords": ["领导人", "总书记", "主席", "政策", "制度", "体制", "民主", "自由", "人权", "独裁", "专制",
                    "境外势力", "外媒", "西方", "美国", "敌对", "渗透", "干涉内政", "颠覆"],
        "desc": "暗讽领导人、质疑政策制度、传播境外口径"
    },
    "sentiment_incite": {
        "name": "舆情煽动",
        "color": "#ffff44",
        "keywords": ["愤怒", "抗议", "不满", "维权", "上访", "请愿", "罢工", "罢课", "集会", "游行", "示威",
                    "官逼民反", "贪腐", "不公", "黑幕", "真相", "揭露", "曝光"],
        "desc": "煽动情绪、制造对立、放大负面、激化矛盾"
    },
    "sensitive_event": {
        "name": "敏感事件",
        "color": "#aa44ff",
        "keywords": ["六四", "天安门", "89", "64", "法轮功", "轮子", "台独", "藏独", "疆独", "港独",
                    "新疆", "西藏", "香港", "台湾", "统一", "独立", "分裂", "颜色革命", "茉莉花"],
        "desc": "引用敏感历史节点、暗示维稳事件、触及红线话题"
    }
}

# 风险等级定义
RISK_LEVELS = {
    "high": {"name": "高危", "color": "#ff4444", "size": 35, "border": 4},
    "medium": {"name": "中危", "color": "#ffaa00", "size": 25, "border": 2},
    "low": {"name": "低危", "color": "#44bb44", "size": 18, "border": 1}
}

# ============================================
# 阶段1：敏感点识别 Prompt
# ============================================

SENSITIVE_SCAN_PROMPT = """
你是互联网内容审核专家，专门识别不符合中国官方宣传口径的敏感内容。

请仔细分析以下文本，识别其中的敏感点：

【敏感维度】
1. 历史虚无 (history_nihilism): 否定党史、抹黑英烈、美化反面人物、歪曲重大历史事件
2. 政治立场 (political_stance): 暗讽领导人、质疑政策制度、传播境外口径
3. 舆情煽动 (sentiment_incite): 煽动情绪、制造对立、放大负面、激化矛盾
4. 敏感事件 (sensitive_event): 引用敏感历史节点、暗示维稳事件、触及红线话题

【特别注意】
- 识别隐晦表达：反话、讽刺、"阴阳怪气"、借古讽今
- 识别隐喻指代：用代号、谐音、历史典故暗指敏感内容
- 识别立场倾向：作者是在批评还是支持，是客观陈述还是带有倾向

【输出格式】
返回 JSON 数组，每个敏感点包含：
- "content": 原文中的敏感内容（保留原文）
- "dimension": 敏感维度代码
- "risk_level": 风险等级 (high/medium/low)
- "interpretation": 这段话实际在暗示/表达什么
- "entities": 涉及的实体（人物、组织、事件）列表
- "stance": 作者立场 (attack/support/neutral/sarcasm)

若无敏感内容，返回 []。

【待分析文本】
{text}
"""

# ============================================
# 阶段2：关系构建 Prompt
# ============================================

RELATION_BUILD_PROMPT = """
基于已识别的敏感点，构建实体关系网络。

【已识别敏感点】
{sensitive_points}

【原文】
{text}

【任务】
1. 提取所有涉及的实体（人物、组织、事件、概念）
2. 构建实体之间的关系，特别关注：
   - 攻击/批评关系（谁在批评/攻击谁）
   - 支持/辩护关系（谁在为谁辩护）
   - 隐晦指向（用A暗喻B的关系）
   - 对立关系（哪些实体站在对立面）

【输出格式】
返回 JSON 数组，每个关系包含：
- "head": 主体实体
- "relation": 关系描述（保留具体动作）
- "tail": 客体实体
- "type_head": 实体类型 (Person/Org/Event/Concept)
- "type_tail": 实体类型
- "relation_type": 关系类型 (attack/support/imply/oppose/neutral)
- "risk_level": 这条关系的风险等级 (high/medium/low)
- "evidence": 支撑这个关系的原文证据
"""

# ============================================
# 隐喻/暗示识别 Prompt
# ============================================

METAPHOR_PROMPT = """
分析以下文本中的隐晦表达和深层含义：

【文本】
{text}

【分析维度】
1. **暗讽识别**：是否使用反话、讽刺、"阴阳怪气"？具体是在讽刺什么？
2. **隐喻解读**：如果使用了隐喻、典故、代号、谐音，实际在指向什么？
3. **借古讽今**：是否借历史事件/人物暗喻当前？指向的是什么？
4. **立场判断**：作者的真实立场是什么？表面中立实际在表达什么？
5. **传播风险**：这段内容如果传播，可能被如何解读？

【输出格式】
返回 JSON：
{{
  "has_metaphor": true/false,
  "metaphors": [
    {{
      "surface": "表面表达",
      "actual_meaning": "实际含义",
      "target": "指向的敏感目标",
      "technique": "使用的技巧(反讽/隐喻/借古讽今/谐音等)"
    }}
  ],
  "author_stance": "作者真实立场",
  "risk_assessment": "传播风险评估"
}}
"""

# ============================================
# 关系推理 Prompt
# ============================================

INFERENCE_PROMPT = """
基于已抽取的关系，推理隐含关联：

【已知关系】
{existing_relations}

【推理任务】
1. 如果 A攻击B，B攻击C，那么A和C是什么关系？
2. 哪些实体虽然没有直接关联，但属于同一阵营？
3. 哪些实体处于对立阵营？
4. 这些关系揭示了什么核心矛盾或敏感主题？

【输出格式】
返回 JSON：
{{
  "inferred_relations": [
    {{"head": "实体A", "relation": "推理出的关系", "tail": "实体B", "confidence": 0.8}}
  ],
  "camps": [
    {{"name": "阵营名称", "members": ["实体1", "实体2"], "stance": "立场描述"}}
  ],
  "core_conflicts": ["核心矛盾1", "核心矛盾2"],
  "main_sensitive_theme": "核心敏感主题"
}}
"""

# ============================================
# 辅助函数
# ============================================

def smart_split(text, max_len=CHUNK_LEN):
    """按段落边界分块，保持语义完整性"""
    paragraphs = re.split(r'\n\s*\n|\n(?=[第一二三四五六七八九十\d]+[章节条款])', text)
    chunks = []
    current = ""
    
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(current) + len(p) + 1 < max_len:
            current += "\n\n" + p if current else p
        else:
            if current:
                chunks.append(current.strip())
            if len(p) > max_len:
                sentences = re.split(r'(?<=[。！？；])', p)
                sub_chunk = ""
                for s in sentences:
                    if len(sub_chunk) + len(s) < max_len:
                        sub_chunk += s
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk.strip())
                        sub_chunk = s
                if sub_chunk:
                    current = sub_chunk
                else:
                    current = ""
            else:
                current = p
    
    if current:
        chunks.append(current.strip())
    
    return chunks if chunks else [text[:max_len]]

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

@st.cache_resource
def get_client(api_key):
    return genai.Client(api_key=api_key)

def parse_json_response(text):
    """安全解析 LLM 返回的 JSON"""
    text = text.replace("```json", "").replace("```", "").strip()
    # 尝试找到 JSON 数组或对象
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        end = text.rfind(end_char) + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except:
                continue
    return [] if "[" in text else {}

# ============================================
# 阶段1：敏感点扫描
# ============================================

def scan_sensitive_points(chunk_data, client, model):
    """扫描文本块中的敏感点"""
    i, text = chunk_data
    prompt = SENSITIVE_SCAN_PROMPT.format(text=text)
    
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        points = parse_json_response(resp.text)
        if isinstance(points, list):
            for p in points:
                p["source_chunk"] = i
                p["source_text"] = text[:200] + "..." if len(text) > 200 else text
            return points
    except Exception as e:
        print(f"[scan chunk {i}] error: {e}")
    return []

# ============================================
# 阶段2：关系构建
# ============================================

def build_relations(sensitive_points, text, client, model):
    """基于敏感点构建关系网络"""
    if not sensitive_points:
        return []
    
    points_summary = json.dumps(sensitive_points[:20], ensure_ascii=False, indent=2)
    prompt = RELATION_BUILD_PROMPT.format(
        sensitive_points=points_summary,
        text=text[:3000]
    )
    
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        relations = parse_json_response(resp.text)
        return relations if isinstance(relations, list) else []
    except Exception as e:
        print(f"[build relations] error: {e}")
    return []

# ============================================
# 隐喻识别
# ============================================

def detect_metaphors(text, client, model):
    """检测隐喻和暗示"""
    prompt = METAPHOR_PROMPT.format(text=text[:2500])
    
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        result = parse_json_response(resp.text)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        print(f"[metaphor] error: {e}")
    return {}

# ============================================
# 关系推理
# ============================================

def infer_relations(existing_relations, client, model):
    """推理隐含关系"""
    if len(existing_relations) < 3:
        return {}
    
    relations_summary = json.dumps(existing_relations[:30], ensure_ascii=False, indent=2)
    prompt = INFERENCE_PROMPT.format(existing_relations=relations_summary)
    
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        result = parse_json_response(resp.text)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        print(f"[inference] error: {e}")
    return {}

# ============================================
# 构建可视化图谱
# ============================================

def build_graph(relations, sensitive_points, inference_result):
    """构建带风险等级的知识图谱"""
    G = nx.DiGraph()
    
    # 统计实体风险等级
    entity_risks = defaultdict(lambda: {"high": 0, "medium": 0, "low": 0})
    
    for r in relations:
        head = r.get("head", "")
        tail = r.get("tail", "")
        risk = r.get("risk_level", "low")
        if head:
            entity_risks[head][risk] += 1
        if tail:
            entity_risks[tail][risk] += 1
    
    # 从敏感点提取实体风险
    for p in sensitive_points:
        risk = p.get("risk_level", "low")
        for entity in p.get("entities", []):
            entity_risks[entity][risk] += 1
    
    def get_entity_risk(entity):
        risks = entity_risks.get(entity, {"high": 0, "medium": 0, "low": 0})
        if risks["high"] > 0:
            return "high"
        elif risks["medium"] > 0:
            return "medium"
        return "low"
    
    def get_dimension_color(relation):
        """根据关系类型返回颜色"""
        rel_type = relation.get("relation_type", "neutral")
        if rel_type == "attack":
            return "#ff4444"
        elif rel_type == "support":
            return "#44bb44"
        elif rel_type == "imply":
            return "#aa44ff"
        elif rel_type == "oppose":
            return "#ffaa00"
        return "#7f8ea3"
    
    # 添加节点和边
    for r in relations:
        head = r.get("head", "").strip()
        tail = r.get("tail", "").strip()
        relation_text = r.get("relation", "")
        
        if not head or not tail:
            continue
        
        head_risk = get_entity_risk(head)
        tail_risk = get_entity_risk(tail)
        
        head_style = RISK_LEVELS[head_risk]
        tail_style = RISK_LEVELS[tail_risk]
        
        # 添加节点
        G.add_node(head, 
            label=head, 
            color=head_style["color"],
            size=head_style["size"],
            borderWidth=head_style["border"],
            title=f"风险等级: {head_style['name']}"
        )
        G.add_node(tail, 
            label=tail, 
            color=tail_style["color"],
            size=tail_style["size"],
            borderWidth=tail_style["border"],
            title=f"风险等级: {tail_style['name']}"
        )
        
        # 添加边
        edge_color = get_dimension_color(r)
        rel_type = r.get("relation_type", "neutral")
        dashes = rel_type == "imply"  # 暗示关系用虚线
        
        label = relation_text if len(relation_text) <= 20 else relation_text[:17] + "..."
        G.add_edge(head, tail, 
            label=label,
            color=edge_color,
            dashes=dashes,
            arrows="to",
            title=r.get("evidence", "")[:100] if r.get("evidence") else ""
        )
    
    # 添加推理出的关系
    if inference_result and "inferred_relations" in inference_result:
        for r in inference_result["inferred_relations"]:
            head = r.get("head", "").strip()
            tail = r.get("tail", "").strip()
            if head and tail and not G.has_edge(head, tail):
                if head not in G:
                    G.add_node(head, label=head, color="#7f8ea3", size=15)
                if tail not in G:
                    G.add_node(tail, label=tail, color="#7f8ea3", size=15)
                G.add_edge(head, tail,
                    label=r.get("relation", "推理关联"),
                    color="#9966ff",
                    dashes=True,
                    arrows="to",
                    title=f"置信度: {r.get('confidence', 0.5)}"
                )
    
    return G

# ============================================
# 生成报告
# ============================================

def generate_report(sensitive_points, relations, inference_result, metaphor_results):
    """生成分析报告"""
    rpt = "# 🔍 DeepGraph Pro v3 敏感内容分析报告\n\n"
    
    # 统计摘要
    high_count = sum(1 for p in sensitive_points if p.get("risk_level") == "high")
    medium_count = sum(1 for p in sensitive_points if p.get("risk_level") == "medium")
    low_count = sum(1 for p in sensitive_points if p.get("risk_level") == "low")
    
    rpt += "## 📊 风险统计\n\n"
    rpt += f"- 🔴 高危敏感点: {high_count}\n"
    rpt += f"- 🟠 中危敏感点: {medium_count}\n"
    rpt += f"- 🟢 低危敏感点: {low_count}\n"
    rpt += f"- 📈 关系总数: {len(relations)}\n\n"
    
    # 维度分布
    dim_counts = defaultdict(int)
    for p in sensitive_points:
        dim = p.get("dimension", "unknown")
        dim_counts[dim] += 1
    
    rpt += "## 🎯 敏感维度分布\n\n"
    for dim, info in SENSITIVE_DIMENSIONS.items():
        count = dim_counts.get(dim, 0)
        if count > 0:
            rpt += f"- **{info['name']}**: {count} 处\n"
    rpt += "\n"
    
    # 高危敏感点详情
    high_points = [p for p in sensitive_points if p.get("risk_level") == "high"]
    if high_points:
        rpt += "## 🚨 高危敏感点详情\n\n"
        for i, p in enumerate(high_points[:10], 1):
            dim = p.get("dimension", "unknown")
            dim_name = SENSITIVE_DIMENSIONS.get(dim, {}).get("name", dim)
            rpt += f"### {i}. [{dim_name}]\n"
            rpt += f"**原文**: {p.get('content', '')[:200]}...\n\n"
            rpt += f"**解读**: {p.get('interpretation', '')}\n\n"
            rpt += f"**涉及实体**: {', '.join(p.get('entities', []))}\n\n"
            rpt += "---\n\n"
    
    # 核心矛盾
    if inference_result and inference_result.get("core_conflicts"):
        rpt += "## ⚔️ 核心矛盾\n\n"
        for conflict in inference_result["core_conflicts"]:
            rpt += f"- {conflict}\n"
        rpt += "\n"
    
    # 阵营分析
    if inference_result and inference_result.get("camps"):
        rpt += "## 🏴 阵营分析\n\n"
        for camp in inference_result["camps"]:
            rpt += f"**{camp.get('name', '未命名')}**: {', '.join(camp.get('members', []))}\n"
            rpt += f"- 立场: {camp.get('stance', '')}\n\n"
    
    # 隐喻分析
    if metaphor_results and metaphor_results.get("has_metaphor"):
        rpt += "## 🎭 隐喻/暗示分析\n\n"
        for m in metaphor_results.get("metaphors", [])[:5]:
            rpt += f"- **表面**: {m.get('surface', '')}\n"
            rpt += f"  - **实际含义**: {m.get('actual_meaning', '')}\n"
            rpt += f"  - **指向目标**: {m.get('target', '')}\n"
            rpt += f"  - **技巧**: {m.get('technique', '')}\n\n"
    
    return rpt

# ============================================
# 主流程
# ============================================

def main_run(files, api_key, model):
    client = get_client(api_key)
    
    # 提取文本
    all_text = ""
    for f in files:
        txt = extract_text(f)
        if len(txt) > 100:
            all_text += txt + "\n\n"
    
    if not all_text:
        return None, "❌ 文件内容为空或读取失败", [], {}
    
    # 智能分块
    chunks = [(i, c) for i, c in enumerate(smart_split(all_text)) if len(c) > 50]
    
    if not chunks:
        return None, "❌ 文件内容过短", [], {}
    
    # ===== 阶段1: 敏感点扫描 =====
    st.info(f"🔍 阶段1: 扫描 {len(chunks)} 个文本块的敏感内容...")
    bar = st.progress(0)
    all_sensitive_points = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = [exe.submit(scan_sensitive_points, c, client, model) for c in chunks]
        for i, f in enumerate(concurrent.futures.as_completed(futures)):
            if result := f.result():
                all_sensitive_points.extend(result)
            bar.progress((i + 1) / len(chunks))
    
    st.success(f"✅ 阶段1完成: 发现 {len(all_sensitive_points)} 个敏感点")
    
    # ===== 阶段2: 关系构建 =====
    st.info("🔗 阶段2: 构建敏感实体关系网络...")
    all_relations = build_relations(all_sensitive_points, all_text, client, model)
    st.success(f"✅ 阶段2完成: 构建 {len(all_relations)} 条关系")
    
    # ===== 隐喻识别 =====
    st.info("🎭 识别隐喻和暗示...")
    # 对高危敏感点进行隐喻分析
    high_risk_texts = [p.get("content", "") for p in all_sensitive_points if p.get("risk_level") == "high"]
    metaphor_text = "\n---\n".join(high_risk_texts[:5]) if high_risk_texts else all_text[:2000]
    metaphor_results = detect_metaphors(metaphor_text, client, model)
    
    # ===== 关系推理 =====
    st.info("🧠 推理隐含关系...")
    inference_result = infer_relations(all_relations, client, model)
    
    # ===== 构建图谱 =====
    st.info("📊 生成可视化图谱...")
    G = build_graph(all_relations, all_sensitive_points, inference_result)
    
    # ===== 生成报告 =====
    report = generate_report(all_sensitive_points, all_relations, inference_result, metaphor_results)
    
    return G, report, all_sensitive_points, inference_result

# ============================================
# 界面
# ============================================

st.title("🔍 DeepGraph Pro v3")
st.markdown("**敏感内容深度分析系统** - 识别不符合宣传口径的隐晦表达")

with st.sidebar:
    st.header("⚙️ 配置")
    api_key = st.text_input("Google API Key", type="password")
    model_id = st.text_input("Model ID", value="gemini-2.0-flash-exp")
    
    st.markdown("---")
    st.markdown("""
    ### 🎨 风险等级图例
    - 🔴 **高危**: 明确违反口径
    - 🟠 **中危**: 需要审核
    - 🟢 **低危**: 可以忽略
    
    ### 🎯 敏感维度
    - 📕 历史虚无
    - 📙 政治立场
    - 📒 舆情煽动
    - 📘 敏感事件
    """)

col1, col2 = st.columns([1, 2.2])

with col1:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    files = st.file_uploader("上传文件 (PDF/DOCX/EPUB/TXT)", accept_multiple_files=True)
    st.markdown("<br>", unsafe_allow_html=True)
    start = st.button("🚀 开始深度分析")
    st.markdown("</div>", unsafe_allow_html=True)
    
    if st.session_state.processed:
        st.download_button("📥 下载图谱 HTML", st.session_state.graph_html, "graph.html", "text/html")
        st.download_button("📥 下载分析报告", st.session_state.report_txt, "report.md", "text/markdown")

with col2:
    status = "就绪"
    if start:
        status = "分析中"
    if st.session_state.processed:
        status = "完成"
    
    st.markdown(
        f"""
        <div class='glass-card' style='padding:12px 16px; display:flex; gap:10px; align-items:center;'>
          <span style='padding:6px 12px; border-radius:999px; background:rgba(74,224,200,0.18); color:#4ae0c8; font-weight:800;'>{status}</span>
          <span style='color:#cbd5e1;'>两阶段抽取 · 隐喻识别 · 关系推理 · 风险分级</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    if start:
        if not api_key or not files:
            st.error("请填入 API Key 并上传文件")
        else:
            with st.spinner("深度分析中..."):
                G, report, sensitive_points, inference = main_run(files, api_key, model_id)
                if G and len(G.nodes()) > 0:
                    net = Network(
                        height="750px",
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
      "gravitationalConstant": -120,
      "centralGravity": 0.008,
      "springLength": 150,
      "springConstant": 0.08,
      "damping": 0.85,
      "avoidOverlap": 1.0
    },
    "stabilization": { "enabled": true, "iterations": 1000, "updateInterval": 25 }
  },
  "edges": { "smooth": {"type": "continuous"} },
  "interaction": { "dragNodes": true, "hover": true, "navigationButtons": true, "tooltipDelay": 100 }
}
                    """)
                    st.session_state.graph_html = net.generate_html()
                    st.session_state.report_txt = report
                    st.session_state.sensitive_points = sensitive_points
                    st.session_state.processed = True
                    st.rerun()
                elif report:
                    st.warning(report)
    
    if st.session_state.processed:
        # 显示敏感点统计
        points = st.session_state.sensitive_points
        high = sum(1 for p in points if p.get("risk_level") == "high")
        medium = sum(1 for p in points if p.get("risk_level") == "medium")
        
        cols = st.columns(3)
        with cols[0]:
            st.metric("🔴 高危", high)
        with cols[1]:
            st.metric("🟠 中危", medium)
        with cols[2]:
            st.metric("📊 总敏感点", len(points))
        
        # 显示图谱
        st.components.v1.html(st.session_state.graph_html, height=750)
        
        # 显示报告
        with st.expander("📋 查看完整分析报告", expanded=False):
            st.markdown(st.session_state.report_txt)
