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
    page_title="DeepGraph Pro v2",
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
.doc-type-badge {
  display:inline-block; padding:6px 14px; border-radius:999px; font-weight:600; font-size:0.85em;
  background:rgba(74,224,200,0.18); color:#4ae0c8; margin:4px 0;
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
if "doc_type" not in st.session_state:
    st.session_state.doc_type = "auto"
if "detected_type" not in st.session_state:
    st.session_state.detected_type = ""

# --- 参数配置 ---
MAX_WORKERS = 8
CHUNK_LEN = 3000
STOP_REL = {"是","有","存在","包含","涉及","包括","进行","开展","属于","位于","担任","任职"}

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

# ============================================
# 模块1：材料类型定义与分类
# ============================================

DOCUMENT_TYPES = {
    "political_sensitive": "政治/历史敏感",
    "regulatory": "法规/政策文件", 
    "narrative": "历史叙事/传记",
    "opinion": "舆情/评论",
    "economic": "经济/商业",
    "general": "通用内容"
}

CLASSIFY_PROMPT = """
分析以下文本片段，判断其主要属于哪种类型。仅返回类型代码，不要其他内容。

类型选项：
- political_sensitive：政治/历史敏感内容（涉及群体事件、维稳、高层斗争、政治运动、敏感历史等）
- regulatory：法规/政策文件（法律条款、规定、处罚措施、政策通知）
- narrative：历史叙事/传记（时间线、人物故事、回忆录、历史记述）
- opinion：舆情/评论（情感表达、立场观点、网络评论、新闻评论）
- economic：经济/商业（企业、市场、金融、商业活动）
- general：通用内容（以上都不符合）

文本片段：
{text}

仅返回类型代码（如 political_sensitive），不要其他内容：
"""

# ============================================
# 模块2：动态 Prompt 模板系统
# ============================================

PROMPTS = {
    "political_sensitive": """
你是信息抽取助手，面向政治/历史敏感文本，提取 SVO 有向三元组。
字段: head(主体/发起者), relation(精确谓语), tail(客体/承受者), direction(active|passive),
type_head/type_tail ∈ [Person, Org, Event, Location, Outcome, Unknown]。

重点抽取与以下内容相关的关系：
- 群体事件、反党/颠覆、分裂/独立
- 重大维稳/封禁/删除/下架/约谈/抓捕
- 军政机密/调动、涉外摩擦、高层斗争
- 反腐大案、重大监管/行业整顿

第一人称叙述若涉及上述敏感事件或高层主体，也应保留；日常礼节或琐事可忽略。
若文本无敏感事件或重要主体/动作，返回 []。
方向：出现"被/遭/逮捕/拘留/镇压/封禁/删除"等判定 passive，其余 active。
谓语保留原文动词，不用"是/有/进行/开展"等泛化词。
按风险和主体级别排序输出。

返回 JSON 数组格式。仅依据下列文本，不要使用外部知识：
{text}
""",

    "regulatory": """
你是法规政策分析助手，从法规/政策文本中提取结构化的 SVO 三元组。
字段: head(主体/执行者), relation(行为/规定), tail(客体/对象), direction(active|passive),
type_head/type_tail ∈ [Person, Org, Event, Location, Outcome, Unknown]。

重点抽取：
- 监管主体与被监管对象的关系
- 违规行为与处罚措施
- 权利义务关系
- 禁止/允许/要求等规范性行为
- 条款之间的引用和递进关系

保留具体的条款编号、处罚金额、时限等细节作为 relation 的一部分。
若文本无明确的规范性内容，返回 []。

返回 JSON 数组格式。仅依据下列文本：
{text}
""",

    "narrative": """
你是历史叙事分析助手，从传记/历史文本中提取人物关系和事件链的 SVO 三元组。
字段: head(主体), relation(动作/关系), tail(客体), direction(active|passive),
type_head/type_tail ∈ [Person, Org, Event, Location, Outcome, Unknown]。

重点抽取：
- 人物之间的关系（上下级、亲属、对立、合作）
- 重要事件的参与者和影响
- 时间线上的因果关系
- 人物的立场转变和决策
- 隐喻和暗示中的实际指向（需推理）

注意区分"作者观点"和"事实陈述"，在 relation 中标注。
第一人称叙述需识别"我"的真实身份。
若文本仅为日常琐事，返回 []。

返回 JSON 数组格式。仅依据下列文本：
{text}
""",

    "opinion": """
你是舆情评论分析助手，从评论/观点文本中提取立场和情感相关的 SVO 三元组。
字段: head(评论主体/观点持有者), relation(态度/行为), tail(评论对象/观点内容), direction(active|passive),
type_head/type_tail ∈ [Person, Org, Event, Location, Outcome, Unknown]。

重点抽取：
- 评论者对事件/人物的态度（支持/反对/质疑/讽刺）
- 情感倾向和立场表达
- 攻击性言论的主体和对象
- 反讽和隐晦表达的真实含义（需推理）
- 网络用语和缩写的实际指向

在 relation 中标注情感极性：[正面]/[负面]/[中性]/[讽刺]
识别"阴阳怪气"等隐晦表达。
若文本无明确立场表达，返回 []。

返回 JSON 数组格式。仅依据下列文本：
{text}
""",

    "economic": """
你是商业经济分析助手，从财经/商业文本中提取企业关系和市场事件的 SVO 三元组。
字段: head(主体), relation(行为/关系), tail(客体), direction(active|passive),
type_head/type_tail ∈ [Person, Org, Event, Location, Outcome, Unknown]。

重点抽取：
- 企业之间的关系（收购/合作/竞争/投资）
- 高管任命和人事变动
- 市场行为（上市/融资/并购/破产）
- 监管处罚和合规事件
- 财务数据和业绩变化

保留具体金额、股权比例、时间等数据。
若文本无商业相关内容，返回 []。

返回 JSON 数组格式。仅依据下列文本：
{text}
""",

    "general": """
你是通用信息抽取助手，提取文本中的 SVO 三元组。
字段: head(主体), relation(关系/动作), tail(客体), direction(active|passive),
type_head/type_tail ∈ [Person, Org, Event, Location, Outcome, Unknown]。

提取所有有意义的实体关系，包括：
- 人物与组织的关系
- 事件的参与者
- 因果关系
- 时空关系

过滤掉过于泛化的关系（如"是"、"有"）。
若文本内容过于简单无法抽取有意义的关系，返回 []。

返回 JSON 数组格式。仅依据下列文本：
{text}
"""
}

# ============================================
# 模块3：智能语义分块
# ============================================

def smart_split(text, max_len=CHUNK_LEN):
    """按段落边界分块，保持语义完整性"""
    # 按多种分隔符切分
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
            # 如果单个段落超长，进行句子级切分
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

# ============================================
# 模块4：LLM 动态实体消歧
# ============================================

MERGE_PROMPT = """
以下是从文档中抽取出的实体列表。请识别指向同一实体的不同表述（别名、简称、代称等）。

规则：
1. 将同一实体的不同表述合并，选择最正式/完整的名称作为标准名
2. 常见的合并情况：简称与全称、职务称呼与人名、代词指代等
3. 仅返回有别名的实体，没有别名的不要返回
4. 如果无法确定是否为同一实体，不要合并

实体列表：
{entities}

返回 JSON 格式，示例：
{{"邓小平": ["小平", "邓公", "邓小平同志"], "中国共产党": ["中共", "党中央", "党"]}}

仅返回 JSON，不要其他内容：
"""

def merge_entities_with_llm(entities, client, model):
    """使用 LLM 自动识别并合并同义实体"""
    if len(entities) < 5:
        return {}
    
    # 限制实体数量避免 prompt 过长
    entity_sample = list(entities)[:200]
    prompt = MERGE_PROMPT.format(entities=", ".join(entity_sample))
    
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        raw = resp.text.strip()
        # 提取 JSON
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            merge_map = json.loads(raw[start:end])
            # 构建反向映射：别名 -> 标准名
            alias_to_canon = {}
            for canon, aliases in merge_map.items():
                for alias in aliases:
                    alias_to_canon[alias] = canon
            return alias_to_canon
    except Exception as e:
        print(f"[merge] error: {e}")
    
    return {}

# ============================================
# 辅助函数
# ============================================

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

def canonicalize(name: str, alias_map: dict = None) -> str:
    """实体标准化，支持动态别名映射"""
    if not name:
        return name
    name = name.strip()
    
    # 优先使用 LLM 生成的别名映射
    if alias_map and name in alias_map:
        return alias_map[name]
    
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

def classify_document(text_sample, client, model):
    """使用 LLM 判断文档类型"""
    # 取文档开头和中间部分的样本
    sample = text_sample[:2000]
    if len(text_sample) > 5000:
        sample += "\n...\n" + text_sample[len(text_sample)//2:len(text_sample)//2+1000]
    
    prompt = CLASSIFY_PROMPT.format(text=sample)
    
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        doc_type = resp.text.strip().lower()
        # 验证返回的类型是否有效
        if doc_type in DOCUMENT_TYPES:
            return doc_type
    except Exception as e:
        print(f"[classify] error: {e}")
    
    return "general"

def analyze_svo(chunk_data, client, model, doc_type):
    """根据文档类型选择对应的 prompt 进行抽取"""
    i, text = chunk_data
    prompt_template = PROMPTS.get(doc_type, PROMPTS["general"])
    prompt = prompt_template.format(text=text)
    
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

# ============================================
# 核心流程
# ============================================

def main_run(files, api_key, model, doc_type="auto"):
    client = get_client(api_key)
    
    # 提取所有文件文本
    all_text = ""
    for f in files:
        txt = extract_text(f)
        if len(txt) > 100:
            all_text += txt + "\n\n"
    
    if not all_text:
        return None, "❌ 文件内容为空或读取失败", False, ""
    
    # Step 1: 材料分类
    if doc_type == "auto":
        st.info("🔍 正在分析文档类型...")
        detected_type = classify_document(all_text, client, model)
        st.success(f"📋 检测到文档类型：**{DOCUMENT_TYPES.get(detected_type, detected_type)}**")
    else:
        detected_type = doc_type
        st.info(f"📋 使用指定类型：**{DOCUMENT_TYPES.get(detected_type, detected_type)}**")
    
    # Step 2: 智能分块
    chunks = []
    for i, chunk in enumerate(smart_split(all_text)):
        if len(chunk) > 50:  # 过滤过短的块
            chunks.append((i, chunk))
    
    if not chunks:
        return None, "❌ 文件内容过短，无法分析", False, detected_type

    st.info(f"🚀 云端引擎启动：使用 **{detected_type}** 模板分析 {len(chunks)} 个语义块...")
    bar = st.progress(0)
    raw = []

    # Step 3: 并行抽取
    max_workers = min(MAX_WORKERS, len(chunks))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = [exe.submit(analyze_svo, c, client, model, detected_type) for c in chunks]
        for i, f in enumerate(concurrent.futures.as_completed(futures)):
            if res := f.result():
                raw.extend(res)
            bar.progress((i + 1) / len(chunks))

    if not raw:
        return None, "❌ 未提取到数据，请检查 API Key 或模型权限", False, detected_type

    # Step 4: LLM 动态实体消歧
    st.info("🔗 正在进行实体消歧...")
    all_entities = set()
    for it in raw:
        if it.get("head"):
            all_entities.add(it["head"])
        if it.get("tail"):
            all_entities.add(it["tail"])
    
    alias_map = merge_entities_with_llm(all_entities, client, model)
    if alias_map:
        st.success(f"✅ 识别到 {len(alias_map)} 个实体别名并已合并")

    # Step 5: 归一化/过滤/评分
    scored = []
    for it in raw:
        h = canonicalize(it.get("head"), alias_map)
        t = canonicalize(it.get("tail"), alias_map)
        r = it.get("relation")
        if not h or not t or not r:
            continue
        if r in STOP_REL:
            continue
        it["head"], it["tail"] = h, t
        it["direction"] = infer_direction(r, default=it.get("direction", "active"))
        ev_score = score_event("", r)
        act_score = max(score_actor(h), score_actor(t))
        total = ev_score + act_score
        it["_score"] = total
        scored.append(it)

    # 对于非政治敏感内容，降低最低分数阈值
    MIN_SCORE = 0 if detected_type != "political_sensitive" else 1
    scored = [it for it in scored if it["_score"] >= MIN_SCORE]
    scored.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # 节点裁剪
    norm, truncated = trim_graph(scored, max_nodes=300, min_nodes=50)

    # 构图
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

    # 社区着色
    if HAS_LOUVAIN and len(G.nodes()) > 0:
        try:
            undi = G.to_undirected()
            part = community_louvain.best_partition(undi, weight="weight")
            palette = ["#4ae0c8","#7c9dff","#c084fc","#22c55e","#f59e0b","#ef4444","#8b5cf6","#0ea5e9"]
            for n, comm in part.items():
                G.nodes[n]["color"] = palette[comm % len(palette)]
        except:
            pass

    # 生成报告
    rpt = "# DeepGraph Pro v2 Report\n\n"
    rpt += f"- 文档类型: {DOCUMENT_TYPES.get(detected_type, detected_type)}\n"
    rpt += f"- 使用模板: {detected_type}\n"
    rpt += f"- 节点数: {len(G.nodes())}\n"
    rpt += f"- 边数: {len(G.edges())}\n"
    if alias_map:
        rpt += f"- 实体合并: {len(alias_map)} 个别名\n"
    if truncated:
        rpt += "- 注意：节点已截断到前 300 个最相关节点（仅影响展示）\n"
    rpt += "\n## 高分关系（按风险/主体分排序，前 200 条）\n\n"
    for it in scored[:200]:
        rpt += f"[{it.get('_score',0)}] {it['head']} --[{it['relation']}]--> {it['tail']} ({it.get('direction','active')})\n"

    return G, rpt, truncated, detected_type

# ============================================
# 界面
# ============================================

st.title("DeepGraph Pro v2 · 智能模板版")

with st.sidebar:
    st.header("⚙️ Settings")
    st.success("✅ 云端环境已就绪")
    api_key = st.text_input("Google API Key", type="password")
    model_id = st.text_input("Model ID", value="gemini-2.0-flash-exp")
    
    st.markdown("---")
    st.subheader("📋 文档类型")
    doc_type_option = st.selectbox(
        "选择文档类型",
        options=["auto", "political_sensitive", "regulatory", "narrative", "opinion", "economic", "general"],
        format_func=lambda x: "🔍 自动检测" if x == "auto" else f"📄 {DOCUMENT_TYPES.get(x, x)}"
    )
    
    st.markdown("""
    **类型说明：**
    - 🔍 自动检测：LLM 自动判断
    - 政治敏感：群体事件、维稳等
    - 法规政策：条款、处罚措施
    - 历史叙事：传记、回忆录
    - 舆情评论：立场、情感分析
    - 经济商业：企业、市场事件
    - 通用内容：其他类型
    """)
    
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
    files = st.file_uploader("Upload Files (PDF/DOCX/EPUB/TXT)", accept_multiple_files=True)
    st.markdown("<br>", unsafe_allow_html=True)
    start = st.button("🚀 Start Analysis")
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.processed:
        st.download_button("📥 Download Graph HTML", st.session_state.graph_html, "graph.html", "text/html")
        st.download_button("📥 Download Report TXT", st.session_state.report_txt, "report.txt", "text/plain")
        
        if st.session_state.detected_type:
            st.markdown(f"""
            <div class="doc-type-badge">
                📋 {DOCUMENT_TYPES.get(st.session_state.detected_type, st.session_state.detected_type)}
            </div>
            """, unsafe_allow_html=True)

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
          <span style='color:#cbd5e1;'>智能模板 SVO 图谱分析（自动分类 · 动态 Prompt）</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if start:
        if not api_key or not files:
            st.error("请填入 API Key 并上传文件")
        else:
            with st.spinner("Analyzing on Cloud..."):
                G, rpt, truncated, detected_type = main_run(files, api_key, model_id, doc_type_option)
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
                    st.session_state.detected_type = detected_type
                    st.rerun()
                elif rpt:
                    st.error(rpt)

    if st.session_state.processed:
        if st.session_state.truncated:
            st.warning("⚠️ 节点已截断至前 300 个最相关节点（仅影响展示，抽取未截断）")
        st.components.v1.html(st.session_state.graph_html, height=820)
