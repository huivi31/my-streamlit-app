import streamlit as st
import os, json, io, tempfile, re, math, time
from typing import List, Optional
from enum import Enum
from collections import defaultdict
import pypdf
from docx import Document
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from pyvis.network import Network
import networkx as nx

st.set_page_config(page_title="解书客", layout="wide", page_icon="📖", initial_sidebar_state="collapsed")

# ============================================
# 党史文献研究院风格 - 中国红 + 庄重严肃
# ============================================
st.markdown("""

<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@700;900&display=swap');
    /* ========== Global Theme: CPC Official Document ========== */
    :root {
        --china-red: #B71C1C;
        --china-red-hover: #D32F2F;
        --gold-main: #FFD700;
        --gold-accent: #DAA520;
        --text-main: #2C2C2C;
        --text-sub: #555555;
        --bg-page: #FAFAFA;
        --bg-card: #FFFFFF;
        --border-color: #E0E0E0;
        --font-serif: "STFangsong", "FangSong", "SimSun", serif;
    }

    /* Standard Reset & Typography */
    .stApp {
        background-color: var(--bg-page);
        color: var(--text-main);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    h1, h2, h3 {
        font-family: var(--font-serif) !important;
        color: var(--china-red) !important;
        font-weight: bold !important;
    }

    /* ========== Widgets Styling ========== */
    
    /* Buttons: Primary Red Action */
    .stButton > button {
        background: linear-gradient(135deg, var(--china-red) 0%, #8B0000 100%) !important;
        color: #FFD700 !important; /* Gold text */
        border: none !important;
        border-radius: 4px !important;
        padding: 0.6rem 1.2rem !important;
        font-family: var(--font-serif) !important;
        font-size: 1.1rem !important;
        letter-spacing: 0.1em !important;
        box-shadow: 0 4px 6px rgba(139, 0, 0, 0.2);
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(139, 0, 0, 0.3);
    }
    
    /* Tabs: Official Document Style */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
        border-bottom: 2px solid var(--border-color);
        padding-bottom: 0px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent !important;
        border: none !important;
        color: var(--text-sub) !important;
        font-family: var(--font-serif) !important;
        font-size: 1.1rem !important;
    }
    .stTabs [aria-selected="true"] {
        color: var(--china-red) !important;
        border-bottom: 3px solid var(--china-red) !important;
        font-weight: bold !important;
        background-color: rgba(183, 28, 28, 0.05) !important;
    }

    /* Text Inputs */
    .stTextInput > div > div > input {
        border: 1px solid var(--border-color);
        border-radius: 4px;
        padding: 0.5rem;
    }
    .stTextInput > div > div > input:focus {
        border-color: var(--china-red) !important;
        box-shadow: 0 0 0 2px rgba(183, 28, 28, 0.2) !important;
    }

    /* Cards / Containers */
    [data-testid="stVerticalBlock"] {
        gap: 1rem;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #F8F9FA;
        border-right: 1px solid #E0E0E0;
    }
    
    /* Top Header Bar Adjustments */
    header[data-testid="stHeader"] {
        background-color: transparent !important;
    }

    /* ========== CPC Header Banner (Preserved & Optimized) ========== */
    .cpc-header {
        position: relative;
        background: linear-gradient(90deg, #D32F2F 0%, #C62828 50%, #B71C1C 100%);
        padding: 20px 0;
        margin: -6rem -4rem 30px -4rem;
        box-shadow: 0 8px 24px rgba(0,0,0,0.5);
        width: calc(100% + 8rem);
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        white-space: nowrap;
        overflow: hidden; /* Prevent scrollbar if font is too big */
    }
    
    .cpc-header::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background: radial-gradient(circle at 50% 50%, rgba(255, 215, 0, 0.1) 0%, transparent 60%);
        pointer-events: none;
    }
    
    .cpc-header-title {
        font-family: "Noto Serif SC", "Source Han Serif SC", "SimSun", serif;
        font-size: 13vw;
        font-weight: 900;
        margin: 0;
        padding: 0 20px;
        letter-spacing: 0.02em;
        line-height: 1.1;
        
        /* 恢复亮金渐变 */
        background: linear-gradient(180deg, #FFFFE0 10%, #FFD700 40%, #DAA520 70%, #FFD700 90%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        
        /* 柔和的深红投影 + 黑色远景虚化 = 悬浮感 */
        filter: drop-shadow(0 2px 0 #800000) drop-shadow(0 5px 10px rgba(0,0,0,0.3));
        
        /* 极细的深色描边增加清晰度，但不过分 */
        -webkit-text-stroke: 1px rgba(139, 0, 0, 0.2);
    }
    
    .decorative-stars {
        position: absolute;
        width: 100%; height: 100%;
        top: 0; left: 0; pointer-events: none; z-index: 0;
    }
    
    .star {
        position: absolute;
        color: #FFD700;
        font-size: 24px;
        opacity: 0.5;
        animation: star-pulse 4s ease-in-out infinite;
        filter: drop-shadow(0 0 5px rgba(255, 215, 0, 0.8));
    }
    
    @keyframes star-pulse {
        0%, 100% { opacity: 0.3; transform: scale(1); }
        50% { opacity: 0.7; transform: scale(1.3); }
    }
    
    .star:nth-child(1) { top: 20%; left: 8%; font-size: 28px; animation-delay: 0s; }
    .star:nth-child(2) { top: 70%; left: 5%; font-size: 20px; animation-delay: 1s; }
    .star:nth-child(3) { top: 30%; right: 8%; font-size: 26px; animation-delay: 2s; }
    .star:nth-child(4) { top: 80%; right: 12%; font-size: 18px; animation-delay: 3s; }
</style>

<!-- CPC Header Banner -->
<div class="cpc-header">
    <div class="decorative-stars">
        <div class="star">★</div>
        <div class="star">★</div>
        <div class="star">★</div>
        <div class="star">★</div>
    </div>
    <h1 class="cpc-header-title">党政历史文献智能化处理</h1>
</div>

""", unsafe_allow_html=True)

# ============================================
# Pydantic Schema - Event-Centric Knowledge Graph
# ============================================

class RiskLevel(str, Enum):
    SAFE = "SAFE"               # 符合官方叙事
    CONTROVERSIAL = "CONTROVERSIAL"  # 有争议/未定论
    HIGH_RISK = "HIGH_RISK"     # 明显违规/历史虚无主义

class EntityType(str, Enum):
    PERSON = "PERSON"           # 政治人物
    LOCATION = "LOCATION"       # 地点
    ORG = "ORG"                  # 组织/党派
    DOCUMENT = "DOCUMENT"       # 文件/著作/决议
    CONCEPT = "CONCEPT"         # 提法/口号/主义

class EventType(str, Enum):
    MEETING = "MEETING"         # 会议
    CONFLICT = "CONFLICT"       # 战争/冲突
    SPEECH = "SPEECH"           # 讲话/发表
    POLICY = "POLICY"           # 政策出台
    MOVEMENT = "MOVEMENT"       # 政治运动

# 移除 RelationType 枚举，改为自由文本关系

class EntityNode(BaseModel):
    """实体节点"""
    id: str = Field(..., description="归一化ID，如 'PER_Mao_Zedong'")
    name: str = Field(..., description="实体标准中文名")
    type: EntityType
    alias: List[str] = Field(default=[], description="文中出现的别名/黑话")

class EventNode(BaseModel):
    """事件节点"""
    id: str = Field(..., description="事件ID，格式：EVT_动词_主体_时间")
    name: str = Field(..., description="事件简述，如'遵义会议召开'")
    type: EventType
    time_str: str = Field(..., description="标准化时间字符串 YYYY-MM-DD")
    description: str = Field(..., description="事件的详细经过描述")
    political_significance: str = Field(..., description="该事件的政治定性/历史意义")
    risk_level: RiskLevel = Field(..., description="根据输入源判断该描述的风险等级")

class RelationEdge(BaseModel):
    """关系边"""
    source_id: str = Field(..., description="源节点ID (Entity 或 Event)")
    target_id: str = Field(..., description="目标节点ID")
    relation: str = Field(..., description="关系动词/动作，如：参与、组织、发起、批评、支持、反对、任命、出席、领导、提出、批准、签署、调任、逮捕、处决、平反等")
    details: str = Field(..., description="关系的具体细节，如'担任组长'、'造成300人伤亡'")
    evidence: str = Field(..., description="原文证据片段")

class HistoricalGraphBatch(BaseModel):
    """单次处理返回的图谱切片"""
    entities: List[EntityNode]
    events: List[EventNode]
    relations: List[RelationEdge]

ENTITY_TYPE_CN = {
    "PERSON": "人物", "LOCATION": "地点", "ORG": "组织",
    "DOCUMENT": "文件", "CONCEPT": "概念"
}

EVENT_TYPE_CN = {
    "MEETING": "会议", "CONFLICT": "冲突", "SPEECH": "讲话",
    "POLICY": "政策", "MOVEMENT": "运动"
}

RISK_LEVEL_CN = {
    "SAFE": "符合官方叙事", "CONTROVERSIAL": "有争议/未定论", "HIGH_RISK": "明显违规"
}

RELATION_TYPE_CN = {
    "PARTICIPATED_IN": "参与", "ORGANIZED": "组织", "OCCURRED_AT": "发生于",
    "CAUSED": "导致", "CONTRADICTS": "驳斥", "DEFINED_AS": "定性为"
}

# ============================================
# Session State
# ============================================
if "step" not in st.session_state:
    st.session_state.step = 1
if "text_content" not in st.session_state:
    st.session_state.text_content = ""
if "chunks" not in st.session_state:
    st.session_state.chunks = []
if "entities" not in st.session_state:
    st.session_state.entities = []
if "events" not in st.session_state:
    st.session_state.events = []
if "relations" not in st.session_state:
    st.session_state.relations = []
if "focus_stats" not in st.session_state:
    st.session_state.focus_stats = {"nodes": 0, "relations": 0}

CHUNK_SIZE = 4000

# ============================================
# File Reading
# ============================================

def ocr_pdf_with_gemini(file_bytes, api_key):
    """Fallback: Batch OCR using Gemini 3 Flash Preview (10 pages per request)"""
    try:
        if not api_key:
            return ""
        
        # Init client
        client = genai.Client(api_key=api_key)
        
        # Load PDF Structure
        try:
            pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            total_pages = len(pdf_reader.pages)
        except Exception as e:
            st.error(f"PDF解析失败，无法分卷: {e}")
            return ""

        full_text = ""
        batch_size = 10 # 10 pages fits well within 8k output token limit
        
        # UI Elements
        st.toast(f"开始全量识别，共 {total_pages} 页，将分 {math.ceil(total_pages/batch_size)} 批处理...", icon="📚")
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        preview_expander = st.expander("实时识别预览 (分卷处理中)", expanded=True)
        preview_area = preview_expander.empty()
        
        # Strict Model
        model_name = "gemini-3-flash-preview"

        for start_idx in range(0, total_pages, batch_size):
            end_idx = min(start_idx + batch_size, total_pages)
            status_text.markdown(f"🚀 正在处理第 **{start_idx+1} - {end_idx}** 页 (共 {total_pages} 页)...")
            
            # Create Batch PDF
            writer = pypdf.PdfWriter()
            # If start_idx not 0, careful with resource referencing if strict, but pypdf usually handles well
            for i in range(start_idx, end_idx):
                writer.add_page(pdf_reader.pages[i])
            
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_batch:
                writer.write(tmp_batch)
                batch_path = tmp_batch.name
                
            try:
                # Upload
                uploaded_file = client.files.upload(file=batch_path)
                
                # Processing Wait
                while uploaded_file.state.name == "PROCESSING":
                    time.sleep(1)
                    uploaded_file = client.files.get(name=uploaded_file.name)
                
                if uploaded_file.state.name == "FAILED":
                    st.error(f"分卷 {start_idx}-{end_idx} 上传处理失败，跳过。")
                    continue

                # Generate Stream
                response_stream = client.models.generate_content_stream(
                    model=model_name,
                    contents=[
                        uploaded_file,
                        "Please transcribe the full text content of this document verbatim. Do not summarize. Just output the text content found in the document."
                    ]
                )
                
                batch_text = ""
                for chunk in response_stream:
                    if chunk.text:
                        batch_text += chunk.text
                        # Preview: Show tail of full text + current batch growing
                        display_text = (full_text[-200:] if full_text else "") + "\n[...接上文...]\n" + batch_text
                        preview_area.markdown(display_text[-1000:] + "...")
                
                full_text += batch_text + "\n"
                
            except Exception as e:
                st.warning(f"⚠️ 分卷 {start_idx}-{end_idx} 识别出现问题: {e}")
                # Don't break, try next batch
            finally:
                if os.path.exists(batch_path):
                    os.remove(batch_path)
            
            # Update Progress
            progress_bar.progress(end_idx / total_pages)

        status_text.success(f"✅ 全文档处理完成！共 {len(full_text)} 字")
        time.sleep(1)
        status_text.empty()
        progress_bar.empty()
        return full_text

    except Exception as e:
        st.error(f"OCR 流程致命错误: {e}")
        return ""


def read_file(f, api_key=None):
    name = getattr(f, "name", "")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    data = f.read()
    if hasattr(f, "seek"):
        f.seek(0)
    
    text = ""
    try:
        if ext == "pdf":
            # 1. Try PyPDF first (Fast & Cheap)
            try:
                for page in pypdf.PdfReader(io.BytesIO(data)).pages:
                    text += (page.extract_text() or "") + "\n"
            except:
                pass # Fail silently to trigger fallback
            
            # 2. Check sufficiency & Trigger OCR
            # Enhanced logic: Raise threshold to 500 to catch watermarked scanned PDFs
            clean_text = text.strip()
            if len(clean_text) < 500:
                if api_key:
                    # Provide feedback to user
                    st.toast(f"正在使用 Gemini Vision 识别扫描文档: {name}...", icon="👁️")
                    ocr_text = ocr_pdf_with_gemini(data, api_key)
                    
                    # Accept OCR result if it's substantial
                    if ocr_text and len(ocr_text) > 100:
                        text = ocr_text
                else:
                    if len(clean_text) < 100:
                        st.warning(f"文件 {name} 似乎是扫描版PDF，需要 API Key 才能进行 OCR 识别。")

        elif ext == "epub":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
                tmp.write(data)
                path = tmp.name
            try:
                book = epub.read_epub(path, options={'ignore_ncx': True})
                for item in book.get_items():
                    if item.get_type() == ebooklib.ITEM_DOCUMENT:
                        soup = BeautifulSoup(item.get_content(), "html.parser")
                        for tag in soup(['script', 'style']):
                            tag.decompose()
                        text += soup.get_text(separator='\n', strip=True) + "\n"
            finally:
                if os.path.exists(path):
                    os.remove(path)
        elif ext in ["docx", "doc"]:
            text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        else:
            text = data.decode("utf-8", errors="ignore")
    except Exception as e:
        st.error(f"读取失败: {e}")
    return re.sub(r'\n{3,}', '\n\n', text).strip()

def split_text_simple(text, size=CHUNK_SIZE):
    """简单切分（备用）"""
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

# ============================================
# LLM Client
# ============================================
@st.cache_resource
def get_client(key):
    return genai.Client(api_key=key)

# ============================================
# 事件切分关键词（规则优先 + 少量 LLM 校验）
# ============================================
EVENT_BREAK_KEYWORDS = [
    # 时间跳跃
    "第二天", "次日", "翌日", "几天后", "数日后", "一周后", "几周后",
    "一个月后", "数月后", "半年后", "一年后", "多年后", "若干年后",
    "转眼", "不久", "随后", "此后", "后来", "最终", "终于",
    # 空间跳跃
    "与此同时", "另一边", "在另一处", "在北京", "在上海", "在延安",
    "回到", "来到", "抵达", "前往", "离开",
    # 新事件标志
    "会议开始", "会议召开", "大会开幕", "会上", "会后",
    "战斗打响", "战役开始", "冲突爆发",
    "发表讲话", "作报告", "发言指出", "宣布",
    "颁布", "出台", "通过决议", "签署",
    # 章节标记
    "第一章", "第二章", "第三章", "第四章", "第五章",
    "一、", "二、", "三、", "四、", "五、",
    "（一）", "（二）", "（三）", "（四）", "（五）",
]

BREAKPOINT_PROMPT = """判断以下两个段落之间是否发生了【明显的事件转移】或【时间/地点的大幅跳跃】。

上一段的结尾: "...{prev_end}"
下一段的开头: "{next_start}..."

如果是同一个事件的延续，输出 NO。
如果是新的事件开始，输出 YES。
只输出 YES 或 NO。"""

def is_obvious_break(para_start: str) -> bool:
    """规则判断：是否为明显的事件断点"""
    for kw in EVENT_BREAK_KEYWORDS:
        if kw in para_start[:50]:
            return True
    return False

def fast_event_chunker(
    book_content: str, 
    min_chunk_size: int = 800,
    max_chunk_size: int = 3000
) -> List[str]:
    """
    快速切分：纯规则，无 LLM 调用
    """
    paragraphs = [p.strip() for p in book_content.split('\n') if p.strip()]
    if len(paragraphs) == 0:
        return [book_content[:max_chunk_size]] if book_content else []
    
    chunks, current_buffer, current_len = [], [], 0

    for para in paragraphs:
        para_len = len(para)
        if not current_buffer:
            current_buffer.append(para)
            current_len += para_len
            continue
        if current_len < min_chunk_size:
            current_buffer.append(para)
            current_len += para_len
            continue
        if current_len + para_len > max_chunk_size:
            chunks.append("\n".join(current_buffer))
            current_buffer = [para]
            current_len = para_len
            continue
        if is_obvious_break(para):
            chunks.append("\n".join(current_buffer))
            current_buffer = [para]
            current_len = para_len
        else:
            current_buffer.append(para)
            current_len += para_len

    if current_buffer:
        chunks.append("\n".join(current_buffer))

    return chunks


def smart_event_chunker_hybrid(
    book_content: str,
    client,
    model: str,
    min_chunk_size: int = 700,
    max_chunk_size: int = 3400,
    llm_budget: int = 35
) -> List[str]:
    """
    混合切分：规则为主，少量 LLM 校验
    - 规则命中直接切分
    - 仅在“不明显”场景使用 LLM，且有调用上限
    """
    paragraphs = [p.strip() for p in book_content.split('\n') if p.strip()]
    if len(paragraphs) == 0:
        return [book_content[:max_chunk_size]] if book_content else []

    chunks, current_buffer, current_len = [], [], 0

    for para in paragraphs:
        para_len = len(para)
        if not current_buffer:
            current_buffer.append(para)
            current_len += para_len
            continue
        if current_len < min_chunk_size:
            current_buffer.append(para)
            current_len += para_len
            continue
        if current_len + para_len > max_chunk_size:
            chunks.append("\n".join(current_buffer))
            current_buffer = [para]
            current_len = para_len
            continue
        if is_obvious_break(para):
            chunks.append("\n".join(current_buffer))
            current_buffer = [para]
            current_len = para_len
            continue

        decision = "NO"
        if llm_budget > 0:
            prev_end = current_buffer[-1][-60:]
            next_start = para[:60]
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=BREAKPOINT_PROMPT.format(prev_end=prev_end, next_start=next_start),
                    config=types.GenerateContentConfig(
                        max_output_tokens=3,
                        temperature=0.0
                    )
                )
                decision = response.text.strip().upper()
            except Exception:
                decision = "NO"
            llm_budget -= 1

        if "YES" in decision:
            chunks.append("\n".join(current_buffer))
            current_buffer = [para]
            current_len = para_len
        else:
            current_buffer.append(para)
            current_len += para_len

    if current_buffer:
        chunks.append("\n".join(current_buffer))

    return chunks

# ============================================
# Extraction with Structured Output + Context Injection
# ============================================
EXTRACTION_PROMPT_WITH_CONTEXT = """你是一个专业的历史政治文献分析专家。请从以下文本中提取实体、事件和关系。

【全局背景】: {global_context}
【前情提要】: {last_event_summary}

【当前文本】:
{text}

**提取要求：**
1. **实体 (entities)**：政治人物、地点、组织、文件/著作、概念/提法
2. **事件 (events)**：会议、冲突、讲话、政策出台、政治运动  
3. **关系 (relations)**：实体与事件之间的所有关系，用具体动词描述

**关系动词示例（尽量使用具体动词）：**
- 人-事件：参与、主持、出席、发起、组织、领导、策划、反对、支持、批评
- 人-人：任命、提拔、批评、支持、反对、逮捕、处决、平反、会见、指示
- 人-组织：加入、领导、创建、退出、改组、担任
- 人-地点：前往、视察、驻守、撤离、抵达
- 事件-事件：导致、引发、促成、中断、延续
- 其他：签署、批准、提出、发表、宣布、颁布、修订、废除

**风险等级判断标准：**
- SAFE: 符合官方历史叙事
- CONTROVERSIAL: 存在争议或未定论
- HIGH_RISK: 明显违背官方叙事、历史虚无主义倾向

**ID规范：**
- 实体ID: PER_姓名 / LOC_地名 / ORG_组织名 / DOC_文件名 / CON_概念名
- 事件ID: EVT_事件简称_年份

**重要：宁可多提取也不要遗漏！每个实体至少要有一条关系。**

请提取所有实体、事件和它们之间的关系，注意保持与前文的ID一致性。"""

def extract_with_context(
    client, 
    model: str, 
    text: str,
    global_context: str = "",
    last_event_summary: str = "无"
) -> HistoricalGraphBatch:
    """使用 Pydantic Schema 进行结构化抽取（带上下文）"""
    try:
        prompt = EXTRACTION_PROMPT_WITH_CONTEXT.format(
            global_context=global_context or "历史政治文献分析",
            last_event_summary=last_event_summary,
            text=text
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=HistoricalGraphBatch
            )
        )
        data = json.loads(response.text)
        return HistoricalGraphBatch(**data)
    except Exception as e:
        st.warning(f"抽取警告: {e}")
        return HistoricalGraphBatch(entities=[], events=[], relations=[])


from concurrent.futures import ThreadPoolExecutor, as_completed

def process_book_pipeline(
    book_text: str,
    client,
    model: str,
    global_context: str = "",
    chunk_mode: str = "hybrid",
    llm_budget: int = 35,
    max_workers: int = 5
) -> List[HistoricalGraphBatch]:
    """
    上下文注入函数（并行优化版）：
    1) 事件切分（混合/纯规则/固定长度）
    2) 并行抽取各块
    3) 返回每块的结构化图谱
    """
    # 大文件用更大的 chunk 减少调用次数
    text_len = len(book_text)
    if text_len > 500000:  # > 500KB
        min_size, max_size = 2000, 6000
    elif text_len > 100000:  # > 100KB
        min_size, max_size = 1200, 4500
    else:
        min_size, max_size = 700, 3400
    
    if chunk_mode == "hybrid":
        raw_chunks = smart_event_chunker_hybrid(
            book_text, client, model,
            min_chunk_size=min_size,
            max_chunk_size=max_size,
            llm_budget=llm_budget
        )
    elif chunk_mode == "fixed":
        raw_chunks = split_text_simple(book_text, size=max_size)
    else:
        raw_chunks = fast_event_chunker(book_text, min_chunk_size=min_size, max_chunk_size=max_size)

    total_chunks = len(raw_chunks)
    
    # 并行抽取（带进度条）
    all_graph_data = [None] * total_chunks
    completed = [0]  # 用列表以便在闭包中修改
    
    progress_bar = st.progress(0, text=f"抽取进度: 0/{total_chunks}")
    
    def extract_chunk(idx, chunk):
        return idx, extract_with_context(
            client, model, chunk,
            global_context=global_context,
            last_event_summary="无"  # 并行时无法串行传递上下文
        )
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(extract_chunk, i, c) for i, c in enumerate(raw_chunks)]
        for future in as_completed(futures):
            idx, result = future.result()
            all_graph_data[idx] = result
            completed[0] += 1
            progress_bar.progress(
                completed[0] / total_chunks, 
                text=f"抽取进度: {completed[0]}/{total_chunks}"
            )
    
    progress_bar.empty()
    return [g for g in all_graph_data if g is not None]


def aggregate_graph_batches(batches: List[HistoricalGraphBatch]):
    """合并多个批次的图谱数据（去重）"""
    all_entities = {}
    all_events = {}
    all_relations = []

    for batch in batches:
        for e in batch.entities:
            if e.id not in all_entities:
                all_entities[e.id] = e.model_dump()
        for ev in batch.events:
            if ev.id not in all_events:
                all_events[ev.id] = ev.model_dump()
        for r in batch.relations:
            all_relations.append(r.model_dump())

    seen = set()
    unique_relations = []
    for r in all_relations:
        key = f"{r['source_id']}|{r['relation']}|{r['target_id']}"
        if key not in seen:
            seen.add(key)
            unique_relations.append(r)

    return list(all_entities.values()), list(all_events.values()), unique_relations


def find_orphan_nodes(entities, events, relations):
    """找出没有任何关系的孤立节点"""
    connected_ids = set()
    for r in relations:
        connected_ids.add(r.get('source_id', ''))
        connected_ids.add(r.get('target_id', ''))
    
    orphan_entities = [e for e in entities if e['id'] not in connected_ids]
    orphan_events = [e for e in events if e['id'] not in connected_ids]
    return orphan_entities, orphan_events


def integrate_orphans(client, model, orphan_entities, orphan_events, all_entities, all_events):
    """为孤立节点推断关系（基于已有图谱上下文）"""
    if not orphan_entities and not orphan_events:
        return []
    
    # 构建上下文：已有的实体和事件
    context_entities = [f"{e['id']}: {e['name']}" for e in all_entities[:50]]
    context_events = [f"{e['id']}: {e['name']} ({e.get('time_str', '')})" for e in all_events[:30]]
    
    orphan_list = []
    for e in orphan_entities:
        orphan_list.append(f"实体 {e['id']}: {e['name']} (类型: {e['type']})")
    for e in orphan_events:
        orphan_list.append(f"事件 {e['id']}: {e['name']} ({e.get('time_str', '')})")
    
    if not orphan_list:
        return []
    
    prompt = f"""以下是一个历史知识图谱中的孤立节点（没有与其他节点建立关系）。
请根据你对中国历史的了解，为这些孤立节点推断合理的关系。

【已有实体】:
{chr(10).join(context_entities)}

【已有事件】:
{chr(10).join(context_events)}

【孤立节点】:
{chr(10).join(orphan_list)}

请为每个孤立节点生成1-3条与已有节点的关系。关系必须符合历史事实。
如果无法确定关系，可以跳过该节点。

返回JSON格式：
{{"relations": [
  {{"source_id": "...", "target_id": "...", "relation": "动词", "details": "具体说明", "evidence": "基于历史常识"}}
]}}
"""
    
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
        return data.get('relations', [])
    except Exception as e:
        st.warning(f"孤立节点整合失败: {e}")
        return []


# ============================================
# 关注度评估与关系过滤（事件中心）
# ============================================
FOCUS_KEYWORDS_STRONG = [
    "总书记", "主席", "军委主席", "总理", "总司令",
    "中央军委", "军委", "政治局", "常委", "中央委员会",
    "国务院", "国家安全", "公安", "国安", "武警",
    "解放军", "战区", "军区", "海军", "空军", "火箭军",
    "国防部", "外交部", "中宣部", "中组部", "人大", "政协"
]
FOCUS_KEYWORDS_MID = [
    "党", "政府", "军", "军队", "部队", "委员会", "党委", "省委", "市委",
    "指挥部", "司令部", "总参", "总后", "总政"
]

EVENT_IMPORTANCE_BASE = {
    "MEETING": 5, "POLICY": 5, "MOVEMENT": 5,
    "CONFLICT": 4, "SPEECH": 4
}

REL_BONUS = {
    "ORGANIZED": 2,
    "DEFINED_AS": 2,
    "CAUSED": 2,
    "PARTICIPATED_IN": 1
}

RISK_BONUS = {"SAFE": 1, "CONTROVERSIAL": 2, "HIGH_RISK": 3}


def _contains_any(text: str, keywords: List[str]) -> bool:
    return any(k and (k in text) for k in keywords)


def compute_entity_importance(e: dict, extra_focus: Optional[List[str]] = None) -> int:
    name = e.get("name", "")
    etype = e.get("type", "")
    base = {"PERSON": 5, "ORG": 4, "DOCUMENT": 3, "CONCEPT": 3, "LOCATION": 2}.get(etype, 2)
    score = base

    if _contains_any(name, FOCUS_KEYWORDS_STRONG):
        score += 4
    if _contains_any(name, FOCUS_KEYWORDS_MID):
        score += 2
    if extra_focus and _contains_any(name, extra_focus):
        score += 3

    return min(score, 10)


def compute_event_importance(ev: dict, extra_focus: Optional[List[str]] = None) -> int:
    base = EVENT_IMPORTANCE_BASE.get(ev.get("type", ""), 3)
    text = f"{ev.get('name','')} {ev.get('political_significance','')}"
    score = base

    if _contains_any(text, FOCUS_KEYWORDS_STRONG):
        score += 3
    if _contains_any(text, FOCUS_KEYWORDS_MID):
        score += 1
    if extra_focus and _contains_any(text, extra_focus):
        score += 2

    score += RISK_BONUS.get(ev.get("risk_level", "SAFE"), 1)
    return min(score, 10)


def prioritize_graph(entities, events, relations, min_weight=5, top_per_event=8, extra_focus: Optional[List[str]] = None):
    entity_score = {e["id"]: compute_entity_importance(e, extra_focus=extra_focus) for e in entities}
    event_score = {ev["id"]: compute_event_importance(ev, extra_focus=extra_focus) for ev in events}

    filtered = []
    event_relations = defaultdict(list)

    for r in relations:
        src, tgt = r.get("source_id"), r.get("target_id")
        if src in event_score or tgt in event_score:
            src_score = event_score.get(src, entity_score.get(src, 2))
            tgt_score = event_score.get(tgt, entity_score.get(tgt, 2))
            rel_bonus = REL_BONUS.get(r.get("relation"), 0)
            weight = min(int((src_score + tgt_score) / 2 + rel_bonus), 10)
            r["weight"] = weight
            filtered.append(r)
            event_id = src if src in event_score else tgt
            event_relations[event_id].append(r)

    keep = set()
    for event_id, rels in event_relations.items():
        rels_sorted = sorted(rels, key=lambda x: x.get("weight", 0), reverse=True)
        for r in rels_sorted[:top_per_event]:
            keep.add(f"{r['source_id']}|{r['relation']}|{r['target_id']}")
        for r in rels_sorted:
            if r.get("weight", 0) >= min_weight:
                keep.add(f"{r['source_id']}|{r['relation']}|{r['target_id']}")

    final_relations = []
    for r in filtered:
        key = f"{r['source_id']}|{r['relation']}|{r['target_id']}"
        if key in keep:
            final_relations.append(r)

    focus_nodes = sum(1 for s in list(entity_score.values()) + list(event_score.values()) if s >= 7)
    focus_relations = sum(1 for r in final_relations if r.get("weight", 0) >= 7)

    return entities, events, final_relations, {"nodes": focus_nodes, "relations": focus_relations}


# 高危关键词（不归入散点容器）
HIGH_RISK_KEYWORDS = [
    "清洗", "肃反", "整风", "批斗", "迫害", "冤案", "平反", "处决", "枪决",
    "丑闻", "腐败", "贪污", "受贿", "双规", "落马", "调查", "审查",
    "政变", "兵变", "叛逃", "暗杀", "遇刺", "自杀", "非正常死亡",
    "六四", "天安门", "反右", "文革", "大跃进", "三年困难",
    "林彪", "四人帮", "江青", "康生", "周永康", "薄熙来", "令计划", "徐才厚", "郭伯雄"
]


def is_high_risk_node(node):
    """判断节点是否涉及高危内容"""
    # 检查事件风险等级
    if node.get("risk_level") in ("HIGH_RISK", "CONTROVERSIAL"):
        return True
    
    # 检查名称和描述是否包含高危关键词
    text = f"{node.get('name', '')} {node.get('description', '')} {node.get('political_significance', '')}"
    for kw in HIGH_RISK_KEYWORDS:
        if kw in text:
            return True
    return False


def find_sparse_nodes(entities, events, relations, max_relations=2):
    """找出关系稀疏的节点"""
    node_relation_count = defaultdict(int)
    for r in relations:
        node_relation_count[r.get("source_id", "")] += 1
        node_relation_count[r.get("target_id", "")] += 1
    
    sparse_entities = [e for e in entities if node_relation_count.get(e["id"], 0) <= max_relations]
    sparse_events = [ev for ev in events if node_relation_count.get(ev["id"], 0) <= max_relations]
    main_entities = [e for e in entities if node_relation_count.get(e["id"], 0) > max_relations]
    main_events = [ev for ev in events if node_relation_count.get(ev["id"], 0) > max_relations]
    
    return main_entities, main_events, sparse_entities, sparse_events


def integrate_sparse_with_search(client, model, sparse_entities, sparse_events, main_entities, main_events):
    """
    用 LLM + 外部知识为散点找主图关联
    返回：新关系列表，未整合的节点列表
    """
    if not sparse_entities and not sparse_events:
        return [], [], []
    
    # 构建主图上下文
    main_entity_names = [f"{e['id']}: {e['name']}" for e in main_entities[:40]]
    main_event_names = [f"{ev['id']}: {ev['name']} ({ev.get('time_str','')})" for ev in main_events[:30]]
    
    # 散点列表
    sparse_list = []
    for e in sparse_entities:
        sparse_list.append({"id": e["id"], "name": e["name"], "type": e.get("type", ""), "is_event": False})
    for ev in sparse_events:
        sparse_list.append({"id": ev["id"], "name": ev["name"], "type": ev.get("type", ""), "time": ev.get("time_str", ""), "is_event": True})
    
    if not sparse_list:
        return [], [], []
    
    prompt = f"""你是中国近现代史专家。以下散点节点在知识图谱中关系稀疏，请根据历史事实为它们找到与主图节点的关联。

【主图实体】:
{chr(10).join(main_entity_names)}

【主图事件】:
{chr(10).join(main_event_names)}

【散点节点】:
{json.dumps(sparse_list, ensure_ascii=False, indent=2)}

**任务：**
1. 根据你对中国历史的了解，为每个散点找1-3条与主图节点的真实关系
2. 关系必须符合历史事实，不能编造
3. 如果某个散点确实与主图无关，将其标记为 unlinked

**返回JSON格式：**
{{
  "new_relations": [
    {{"source_id": "散点ID", "target_id": "主图节点ID", "relation": "动词", "details": "说明", "evidence": "历史依据"}}
  ],
  "unlinked_ids": ["无法关联的散点ID列表"]
}}
"""
    
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
        new_relations = data.get("new_relations", [])
        unlinked_ids = set(data.get("unlinked_ids", []))
        
        # 分离已整合和未整合的散点
        unlinked_entities = [e for e in sparse_entities if e["id"] in unlinked_ids]
        unlinked_events = [ev for ev in sparse_events if ev["id"] in unlinked_ids]
        
        return new_relations, unlinked_entities, unlinked_events
    except Exception as e:
        st.warning(f"散点整合检索失败: {e}")
        return [], sparse_entities, sparse_events


def build_sensitive_node(unlinked_entities, unlinked_events):
    """将无法关联的散点构建为敏感词库节点"""
    if not unlinked_entities and not unlinked_events:
        return None
    
    items = []
    for e in unlinked_entities:
        items.append(f"• {e['name']} ({ENTITY_TYPE_CN.get(e.get('type'), e.get('type'))})")
    for ev in unlinked_events:
        items.append(f"◆ {ev['name']} ({ev.get('time_str', '')})")
    
    return {
        "id": "_SENSITIVE_TERMS_",
        "label": f"敏感词库 ({len(unlinked_entities) + len(unlinked_events)})",
        "items": items,
        "entities": unlinked_entities,
        "events": unlinked_events
    }


# ============================================
# Graph Building - Event-Centric
# ============================================
def build_event_graph(entities, events, relations, sensitive_node=None):
    """构建以事件为中心的图谱"""
    G = nx.DiGraph()
    
    # 颜色配置 - 党史文献风格
    entity_colors = {
        "PERSON": "#c62828", "LOCATION": "#1565c0", "ORG": "#2e7d32",
        "DOCUMENT": "#7b1fa2", "CONCEPT": "#f57c00"
    }
    
    event_colors = {
        "MEETING": "#1565c0", "CONFLICT": "#c62828", "SPEECH": "#2e7d32",
        "POLICY": "#7b1fa2", "MOVEMENT": "#f57c00"
    }
    
    risk_border = {
        "SAFE": "#2e7d32", "CONTROVERSIAL": "#f57c00", "HIGH_RISK": "#c62828"
    }
    
    # 添加实体节点
    entity_map = {e["id"]: e for e in entities}
    for e in entities:
        G.add_node(
            e["id"],
            label=e["name"],
            color=entity_colors.get(e["type"], "#94a3b8"),
            size=20,
            shape="dot",
            title=f"{ENTITY_TYPE_CN.get(e['type'], e['type'])}: {e['name']}"
        )
    
    # 添加事件节点（更大、方形表示）
    event_map = {ev["id"]: ev for ev in events}
    for ev in events:
        risk = ev.get("risk_level", "SAFE")
        bg = event_colors.get(ev.get("type"), "#64748b")
        border = risk_border.get(risk, "#d1d5db")
        G.add_node(
            ev["id"],
            label=ev["name"],
            color={"background": bg, "border": border},
            size=38,
            shape="diamond",
            borderWidth=3,
            borderWidthSelected=5,
            title=(
                f"【{EVENT_TYPE_CN.get(ev.get('type'), ev.get('type'))}】{ev.get('name','')}\n"
                f"时间: {ev.get('time_str', '未知')}\n"
                f"风险: {RISK_LEVEL_CN.get(risk, risk)}\n\n"
                f"{ev.get('description', '')}"
            )
        )
    
    # 添加敏感词库节点
    if sensitive_node:
        items = sensitive_node.get("items", [])
        G.add_node(
            sensitive_node["id"],
            label=sensitive_node["label"],
            color={"background": "#fef3c7", "border": "#f59e0b"},
            size=50,
            shape="box",
            borderWidth=3,
            font={"color": "#92400e", "size": 14, "bold": True},
            title="⚠️ 敏感词库（无法关联到主图）:\n\n" + "\n".join(items[:50]) + ("\n..." if len(items) > 50 else "")
        )
    
    # 添加关系边（使用精选权重，减少冗余）
    for r in relations:
        src, tgt = r["source_id"], r["target_id"]
        if (src in entity_map or src in event_map) and (tgt in entity_map or tgt in event_map):
            w = int(r.get("weight", 5))
            edge_color = "#C41E3A" if w >= 7 else ("#666666" if w >= 5 else "#aaaaaa")
            G.add_edge(
                src, tgt,
                label=r.get("relation", ""),
                title=(r.get("details", "") + ("\n\n证据: " + r.get("evidence", "") if r.get("evidence") else "")),
                color=edge_color,
                width=1 + w / 3
            )
    
    return G

# API Config
with st.container():
    col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
    with col2:
        api_key = st.text_input("API Key", type="password", placeholder="Gemini API Key", label_visibility="collapsed")
    with col3:
        model = st.text_input("Model", value="gemini-3-flash-preview", placeholder="模型名称", label_visibility="collapsed")

st.markdown("<br>", unsafe_allow_html=True)

# Step Navigation
def can_go(target):
    if target == 1:
        return True
    elif target == 2:
        return len(st.session_state.events) > 0
    elif target == 3:
        return len(st.session_state.relations) > 0
    return False

col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 2])

with col2:
    icon = "✓" if st.session_state.step > 1 else ("●" if st.session_state.step == 1 else "○")
    if st.button(f"{icon} 上传", key="nav1", use_container_width=True):
        st.session_state.step = 1
        st.rerun()

with col3:
    icon = "✓" if st.session_state.step > 2 else ("●" if st.session_state.step == 2 else "○")
    if st.button(f"{icon} 审核", key="nav2", use_container_width=True, disabled=not can_go(2)):
        st.session_state.step = 2
        st.rerun()

with col4:
    icon = "✓" if st.session_state.step > 3 else ("●" if st.session_state.step == 3 else "○")
    if st.button(f"{icon} 图谱", key="nav3", use_container_width=True, disabled=not can_go(3)):
        st.session_state.step = 3
        st.rerun()

st.markdown("<hr style='border:none; border-top:1px solid #e5e5e5; margin:20px 0;'>", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### 🔧 工具")
    if st.button("🔄 重新开始", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    
    st.markdown("---")
    st.markdown("**统计**")
    st.write(f"实体: {len(st.session_state.entities)}")
    st.write(f"事件: {len(st.session_state.events)}")
    st.write(f"关系: {len(st.session_state.relations)}")

# ============================================
# Step 1: Upload & Extract
# ============================================
if st.session_state.step == 1:
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # 全局背景输入
        global_context = st.text_area(
            "全局背景（可选）",
            placeholder="简要描述文档主题，如：本书讲述中国共产党1921-1949年发展历程...",
            height=68,
            help="提供背景有助于 LLM 更准确地抽取内容"
        )
        
        # 切分模式
        chunk_mode = st.radio(
            "切分模式",
            ["混合切分（推荐）", "纯规则", "固定长度"],
            horizontal=True,
            help="混合切分：规则+少量 LLM 校验，兼顾准确与速度"
        )
        
        # Recall 优先：默认给更高的 LLM 校验预算，降低误切导致的漏抽
        llm_budget = 35
        if "混合" in chunk_mode:
            llm_budget = st.slider(
                "LLM 断点校验上限",
                min_value=0,
                max_value=120,
                value=35,
                step=5,
                help="Recall 优先：值越大越不容易漏事件（但会变慢）"
            )

        st.markdown("---")
        with st.expander("Advanced Settings", expanded=False):
            focus_extra_raw = st.text_input(
                "额外关注关键词（可选）",
                placeholder="用逗号分隔，例如：党政军,某机构,某职务,某部队...",
                help="会提升你关心的节点/事件权重，帮助保留更多相关关系"
            )
            min_weight = st.slider(
                "保留关系最低权重",
                min_value=1,
                max_value=10,
                value=3,
                step=1,
                help="Recall 优先建议 2-4：越低越不漏（但更冗余）"
            )
            top_per_event = st.slider(
                "每个事件至少保留前 N 条关系",
                min_value=3,
                max_value=30,
                value=12,
                step=1,
                help="Recall 优先建议 10-15：保证每个事件不被剪瘦"
            )
        
        files = st.file_uploader("上传文档", accept_multiple_files=True, type=["pdf", "epub", "docx", "txt"],
                                 label_visibility="collapsed")
        
        if files:
            st.markdown(f"<p style='text-align:center; color:#86868b;'>已选择 {len(files)} 个文件</p>", 
                       unsafe_allow_html=True)
            
            if st.button("开始分析", use_container_width=True):
                if not api_key:
                    st.error("请填写 API Key")
                else:
                    all_text = ""
                    for f in files:
                        all_text += read_file(f, api_key) + "\n\n"
                    
                    if len(all_text.strip()) < 100:
                        st.error("文件内容过少")
                    else:
                        st.session_state.text_content = all_text
                        st.session_state.global_context = global_context
                        client = get_client(api_key)
                        
                        mode = "hybrid" if "混合" in chunk_mode else ("rule" if "规则" in chunk_mode else "fixed")
                        
                        # 上下文注入抽取（分块处理）
                        with st.spinner("正在进行上下文注入抽取..."):
                            batches = process_book_pipeline(
                                all_text, client, model,
                                global_context=global_context,
                                chunk_mode=mode,
                                llm_budget=llm_budget
                            )
                            entities, events, relations = aggregate_graph_batches(batches)
                            
                            # 整合孤立节点
                            orphan_entities, orphan_events = find_orphan_nodes(entities, events, relations)
                            if orphan_entities or orphan_events:
                                st.info(f"🔗 正在整合 {len(orphan_entities)} 个孤立实体, {len(orphan_events)} 个孤立事件...")
                                extra_relations = integrate_orphans(
                                    client, model, 
                                    orphan_entities, orphan_events,
                                    entities, events
                                )
                                relations.extend(extra_relations)

                        extra_focus = [s.strip() for s in (focus_extra_raw or "").split(",") if s.strip()]

                        # 关系去冗余：以事件为中心，确保每个事件有 top-N，同时按权重过滤
                        entities, events, relations, stats = prioritize_graph(
                            entities, events, relations,
                            min_weight=min_weight,
                            top_per_event=top_per_event,
                            extra_focus=extra_focus
                        )
                        st.session_state.focus_stats = stats

                        st.info(f"📄 切分完成: {len(batches)} 块 · 精选后 {len(relations)} 条关系")
                        
                        if events:
                            st.session_state.entities = entities
                            st.session_state.events = events
                            st.session_state.relations = relations
                            st.success(f"✅ 完成: {len(entities)} 实体, {len(events)} 事件, {len(relations)} 关系")
                            st.session_state.step = 2
                            st.rerun()
                        else:
                            st.error("未识别到事件，请检查文档内容")

# ============================================
# Step 2: Review Events & Entities
# ============================================
elif st.session_state.step == 2:
    st.markdown("""
    <div style="text-align:center; padding:30px 0 40px; background: linear-gradient(180deg, rgba(196,30,58,0.05) 0%, #fff 100%);">
        <div class="hero-badge" style="margin-bottom:16px;">内容审核</div>
        <h1 style="font-size:32px; color:#C41E3A; letter-spacing:0.1em;">审核与调整</h1>
        <p style="color:#7a7a7a; font-size:14px;">查看抽取的事件和实体，调整风险等级</p>
    </div>
    """, unsafe_allow_html=True)
    
    entities = st.session_state.entities
    events = st.session_state.events
    relations = st.session_state.relations
    
    # Stats
    focus_stats = st.session_state.focus_stats or {"nodes": 0, "relations": 0}
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("实体数", len(entities))
    with col2:
        st.metric("事件数", len(events))
    with col3:
        st.metric("关系数", len(relations))
    with col4:
        high_risk = sum(1 for e in events if e.get("risk_level") == "HIGH_RISK")
        st.metric("高风险事件", high_risk)
    with col5:
        st.metric("重点节点", focus_stats.get("nodes", 0))
    with col6:
        st.metric("重点关系", focus_stats.get("relations", 0))
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["📅 事件", "👤 实体", "🔗 关系"])
    
    with tab1:
        st.markdown("#### 事件列表（按风险排序）")
        
        # 按风险等级排序
        risk_order = {"HIGH_RISK": 0, "CONTROVERSIAL": 1, "SAFE": 2}
        sorted_events = sorted(events, key=lambda x: risk_order.get(x.get("risk_level", "SAFE"), 2))
        
        for ev in sorted_events:
            risk = ev.get("risk_level", "SAFE")
            risk_class = f"risk-{risk.lower().replace('_', '-')}"
            type_class = f"event-{ev.get('type', 'MEETING').lower()}"
            
            st.markdown(f"""
            <div class="event-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span class="event-title">{ev.get('name', '未知事件')}</span>
                    <span class="risk-tag {risk_class}">{RISK_LEVEL_CN.get(risk, risk)}</span>
                </div>
                <div class="event-meta">
                    <span class="type-tag {type_class}">{EVENT_TYPE_CN.get(ev.get('type'), ev.get('type'))}</span>
                    📅 {ev.get('time_str', '时间未知')}
                </div>
                <div class="event-desc">{ev.get('description', '')}</div>
                <div style="margin-top:10px; padding-top:10px; border-top:1px solid #f0f0f0;">
                    <strong style="font-size:13px; color:#6e6e73;">政治定性:</strong>
                    <span style="font-size:13px; color:#1d1d1f;">{ev.get('political_significance', '未定性')}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    with tab2:
        st.markdown("#### 实体列表")
        
        # 按类型分组
        by_type = defaultdict(list)
        for e in entities:
            by_type[e.get("type", "OTHER")].append(e)
        
        for etype in ["PERSON", "ORG", "LOCATION", "DOCUMENT", "CONCEPT"]:
            if etype not in by_type:
                continue
            elist = by_type[etype]
            type_class = f"type-{etype.lower()}"
            
            with st.expander(f"**{ENTITY_TYPE_CN.get(etype, etype)}** · {len(elist)} 个", expanded=(etype == "PERSON")):
                for e in elist:
                    alias_str = f" ({', '.join(e.get('alias', []))})" if e.get('alias') else ""
                    st.markdown(f"""
                    <div style="padding:8px 12px; margin:4px 0; background:#f5f5f7; border-radius:8px;">
                        <span class="type-tag {type_class}">{etype}</span>
                        <strong>{e.get('name', '')}</strong>
                        <span style="color:#86868b;">{alias_str}</span>
                    </div>
                    """, unsafe_allow_html=True)
    
    with tab3:
        st.markdown("#### 关系列表")
        
        for r in relations[:50]:
            rel_cn = RELATION_TYPE_CN.get(r.get("relation"), r.get("relation"))
            st.markdown(f"""
            <div style="padding:10px 14px; margin:6px 0; background:#f5f5f7; border-radius:8px;">
                <strong>{r.get('source_id', '')}</strong>
                <span style="color:#0071e3; margin:0 8px;">—[ {rel_cn} ]→</span>
                <strong>{r.get('target_id', '')}</strong>
                <div style="font-size:12px; color:#86868b; margin-top:4px;">{r.get('details', '')}</div>
            </div>
            """, unsafe_allow_html=True)
        
        if len(relations) > 50:
            st.markdown(f"<p style='color:#86868b;'>... 还有 {len(relations)-50} 条关系</p>", unsafe_allow_html=True)
    
    # Navigation
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("← 重新上传", use_container_width=True):
                st.session_state.step = 1
                st.rerun()
        with c2:
            if st.button("生成图谱 →", use_container_width=True, type="primary"):
                st.session_state.step = 3
                st.rerun()

# ============================================
# Step 3: Graph Visualization
# ============================================
elif st.session_state.step == 3:
    st.markdown("""
    <div style="text-align:center; padding:30px 0 30px; background: linear-gradient(180deg, rgba(196,30,58,0.05) 0%, #fff 100%);">
        <div class="hero-badge" style="margin-bottom:16px;">可视化展示</div>
        <h1 style="font-size:32px; color:#C41E3A; letter-spacing:0.1em;">事件知识图谱</h1>
        <p style="color:#7a7a7a; font-size:14px;">◆ 菱形为事件节点 &nbsp;|&nbsp; ● 圆形为实体节点</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Filters
    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    with col1:
        show_types = st.multiselect(
            "显示事件类型",
            options=list(EVENT_TYPE_CN.keys()),
            default=list(EVENT_TYPE_CN.keys()),
            format_func=lambda x: EVENT_TYPE_CN.get(x, x)
        )
    with col2:
        show_risks = st.multiselect(
            "显示风险等级",
            options=list(RISK_LEVEL_CN.keys()),
            default=list(RISK_LEVEL_CN.keys()),
            format_func=lambda x: RISK_LEVEL_CN.get(x, x)
        )
    with col3:
        layout = st.selectbox("布局", ["力导向", "层次布局"])
    with col4:
        sparse_threshold = st.number_input("散点补链阈值", min_value=1, max_value=5, value=2, help="关系数≤此值会尝试补链，补不上则进入敏感词库")
    
    # 过滤事件
    filtered_events = [
        e for e in st.session_state.events
        if e.get("type") in show_types and e.get("risk_level", "SAFE") in show_risks
    ]
    
    # 过滤关系（只保留与过滤后事件相关的）
    event_ids = {e["id"] for e in filtered_events}
    filtered_relations = [
        r for r in st.session_state.relations
        if r["source_id"] in event_ids or r["target_id"] in event_ids
    ]
    
    # 过滤实体（只保留有关系的）
    involved_ids = set()
    for r in filtered_relations:
        involved_ids.add(r["source_id"])
        involved_ids.add(r["target_id"])
    
    filtered_entities = [e for e in st.session_state.entities if e["id"] in involved_ids]
    
    # 识别散点（关系稀疏的节点）
    main_entities, main_events, sparse_entities, sparse_events = find_sparse_nodes(
        filtered_entities, filtered_events, filtered_relations, max_relations=sparse_threshold
    )
    
    # 构建敏感词库节点（散点归入此处）
    sensitive_node = build_sensitive_node(sparse_entities, sparse_events)
    
    # 主图只保留关系密集的节点
    main_ids = set([e["id"] for e in main_entities] + [ev["id"] for ev in main_events])
    main_relations = [
        r for r in filtered_relations
        if r.get("source_id") in main_ids and r.get("target_id") in main_ids
    ]
    
    sensitive_count = len(sparse_entities) + len(sparse_events)
    st.markdown(
        f"<p style='text-align:center; color:#86868b;'>主图: {len(main_events)} 事件, {len(main_entities)} 实体, {len(main_relations)} 关系"
        + (f" · <b>敏感词库: {sensitive_count} 项</b>" if sensitive_count > 0 else "") + "</p>", 
        unsafe_allow_html=True
    )
    
    # Build & Display Graph
    G = build_event_graph(main_entities, main_events, main_relations, sensitive_node)
    
    net = Network(height="600px", width="100%", bgcolor="#ffffff", font_color="#1d1d1f", directed=True)
    net.from_nx(G)
    
    if layout == "层次布局":
        net.set_options('''
        {
          "layout": {"hierarchical": {"enabled": true, "direction": "UD", "sortMethod": "directed"}},
          "physics": {"enabled": false},
          "edges": {"smooth": {"type": "cubicBezier"}, "font": {"size": 11}},
          "interaction": {"hover": true, "navigationButtons": true}
        }
        ''')
    else:
        net.set_options('''
        {
          "physics": {
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {"gravitationalConstant": -100, "springLength": 150},
            "stabilization": {"iterations": 200}
          },
          "edges": {"smooth": {"type": "continuous"}, "font": {"size": 11}},
          "interaction": {"hover": true, "navigationButtons": true}
        }
        ''')
    
    st.components.v1.html(net.generate_html(), height=620)
    
    # Legend
    st.markdown("""
    <div style="display:flex; justify-content:center; gap:20px; margin-top:16px; flex-wrap:wrap; padding:12px 20px; background:#fafafa; border:1px solid #e5e5e5;">
        <span style="font-size:12px; color:#4a4a4a;"><span style="color:#1565c0;">◆</span> 会议</span>
        <span style="font-size:12px; color:#4a4a4a;"><span style="color:#c62828;">◆</span> 冲突</span>
        <span style="font-size:12px; color:#4a4a4a;"><span style="color:#2e7d32;">◆</span> 讲话</span>
        <span style="font-size:12px; color:#4a4a4a;"><span style="color:#7b1fa2;">◆</span> 政策</span>
        <span style="font-size:12px; color:#4a4a4a;"><span style="color:#f57c00;">◆</span> 运动</span>
        <span style="color:#ccc;">|</span>
        <span style="font-size:12px; color:#4a4a4a;"><span style="color:#c62828;">●</span> 人物</span>
        <span style="font-size:12px; color:#4a4a4a;"><span style="color:#2e7d32;">●</span> 组织</span>
        <span style="font-size:12px; color:#4a4a4a;"><span style="color:#1565c0;">●</span> 地点</span>
        <span style="font-size:12px; color:#4a4a4a;"><span style="color:#7b1fa2;">●</span> 文件</span>
        <span style="font-size:12px; color:#4a4a4a;"><span style="color:#f57c00;">●</span> 概念</span>
    </div>
    """, unsafe_allow_html=True)
    
    # 敏感词库详情展开
    if sensitive_node:
        sensitive_count = len(sensitive_node.get("items", []))
        with st.expander(f"⚠️ 敏感词库详情 ({sensitive_count} 项)", expanded=False):
            items = sensitive_node.get("items", [])
            st.markdown("\n".join(items[:200]) + ("\n..." if len(items) > 200 else ""))
    
    # Export
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        export_data = {
            "entities": st.session_state.entities,
            "events": st.session_state.events,
            "relations": st.session_state.relations
        }
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "📥 下载 JSON",
                json.dumps(export_data, ensure_ascii=False, indent=2),
                "event_graph.json",
                use_container_width=True
            )
        with c2:
            if st.button("← 返回审核", use_container_width=True):
                st.session_state.step = 2
                st.rerun()
