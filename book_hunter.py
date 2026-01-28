#!/usr/bin/env python3
"""
Book Hunter - 自动搜索、下载图书并生成知识图谱
用法:
    python book_hunter.py --keywords "将军回忆录,军事历史"
    python book_hunter.py --booklist books.txt
    python book_hunter.py --author "粟裕,许世友"
    python book_hunter.py --watch  # 持续监控模式
"""

import os
import sys
import json
import time
import argparse
import requests
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
import re

# ============================================
# 配置
# ============================================
CONFIG = {
    "download_dir": "./downloads",
    "output_dir": "./graphs",
    "processed_db": "./processed_books.json",
    "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
    "gemini_model": "gemini-2.0-flash",
    "max_books_per_run": 10,
    "delay_between_downloads": 5,  # 秒
}

# ============================================
# 书籍搜索源
# ============================================
class BookSource:
    """书籍搜索基类"""
    
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        raise NotImplementedError
    
    def download(self, book_info: Dict, save_path: str) -> bool:
        raise NotImplementedError


class ZLibrarySource(BookSource):
    """Z-Library 搜索源"""
    
    def __init__(self):
        self.base_url = "https://z-library.sk"
        self.search_url = "https://z-library.sk/s/"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
    
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """搜索书籍"""
        results = []
        try:
            # Z-Library 搜索
            search_query = query.replace(" ", "+")
            url = f"{self.search_url}{search_query}"
            
            print(f"[ZLib] 搜索: {query}")
            resp = self.session.get(url, timeout=30)
            
            if resp.status_code == 200:
                # 简单解析（实际需要更复杂的解析）
                # 这里返回模拟数据，实际使用时需要解析 HTML
                print(f"[ZLib] 搜索完成，需要登录后获取结果")
                
        except Exception as e:
            print(f"[ZLib] 搜索错误: {e}")
        
        return results
    
    def download(self, book_info: Dict, save_path: str) -> bool:
        """下载书籍"""
        try:
            download_url = book_info.get("download_url")
            if not download_url:
                return False
            
            resp = self.session.get(download_url, stream=True, timeout=120)
            if resp.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
        except Exception as e:
            print(f"[ZLib] 下载错误: {e}")
        return False


class LibGenSource(BookSource):
    """Library Genesis 搜索源"""
    
    def __init__(self):
        self.mirrors = [
            "https://libgen.is",
            "https://libgen.rs", 
            "https://libgen.st",
        ]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
    
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """搜索 LibGen"""
        results = []
        
        for mirror in self.mirrors:
            try:
                # LibGen JSON API
                api_url = f"{mirror}/json.php"
                params = {
                    "req": query,
                    "lg_topic": "libgen",
                    "open": 0,
                    "view": "simple",
                    "res": limit,
                    "phrase": 1,
                    "column": "def"
                }
                
                print(f"[LibGen] 搜索: {query} @ {mirror}")
                resp = self.session.get(api_url, params=params, timeout=30)
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        for item in data[:limit]:
                            results.append({
                                "title": item.get("title", ""),
                                "author": item.get("author", ""),
                                "year": item.get("year", ""),
                                "extension": item.get("extension", "pdf"),
                                "md5": item.get("md5", ""),
                                "filesize": item.get("filesize", 0),
                                "source": "libgen",
                                "mirror": mirror
                            })
                        if results:
                            print(f"[LibGen] 找到 {len(results)} 本书")
                            break
                    except json.JSONDecodeError:
                        continue
                        
            except Exception as e:
                print(f"[LibGen] {mirror} 错误: {e}")
                continue
        
        return results
    
    def get_download_url(self, md5: str, mirror: str) -> Optional[str]:
        """获取下载链接"""
        try:
            # LibGen 下载页面
            download_page = f"{mirror}/ads.php?md5={md5}"
            resp = self.session.get(download_page, timeout=30)
            
            if resp.status_code == 200:
                # 解析下载链接（简化版）
                # 实际需要解析 HTML 获取真实下载链接
                # 常见格式: https://download.library.lol/main/...
                import re
                matches = re.findall(r'href="(https?://[^"]*get\.php[^"]*)"', resp.text)
                if matches:
                    return matches[0]
                    
                # 备用: library.lol
                matches = re.findall(r'href="(https?://download\.library\.lol[^"]*)"', resp.text)
                if matches:
                    return matches[0]
                    
        except Exception as e:
            print(f"[LibGen] 获取下载链接错误: {e}")
        
        return None
    
    def download(self, book_info: Dict, save_path: str) -> bool:
        """下载书籍"""
        md5 = book_info.get("md5")
        mirror = book_info.get("mirror")
        
        if not md5 or not mirror:
            return False
        
        download_url = self.get_download_url(md5, mirror)
        if not download_url:
            print(f"[LibGen] 无法获取下载链接: {book_info.get('title')}")
            return False
        
        try:
            print(f"[LibGen] 下载中: {book_info.get('title')}")
            resp = self.session.get(download_url, stream=True, timeout=300)
            
            if resp.status_code == 200:
                with open(save_path, 'wb') as f:
                    total = 0
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        total += len(chunk)
                print(f"[LibGen] 下载完成: {total/1024/1024:.1f} MB")
                return True
                
        except Exception as e:
            print(f"[LibGen] 下载错误: {e}")
        
        return False


class AnnaArchiveSource(BookSource):
    """Anna's Archive 搜索源"""
    
    def __init__(self):
        self.base_url = "https://annas-archive.org"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
    
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """搜索 Anna's Archive"""
        results = []
        try:
            search_url = f"{self.base_url}/search"
            params = {
                "q": query,
                "lang": "zh",
                "content": "book_fiction,book_nonfiction",
                "ext": "pdf,epub",
                "sort": "most_relevant"
            }
            
            print(f"[Anna] 搜索: {query}")
            resp = self.session.get(search_url, params=params, timeout=30)
            
            if resp.status_code == 200:
                # 需要解析 HTML
                print(f"[Anna] 搜索完成，需要解析结果页面")
                
        except Exception as e:
            print(f"[Anna] 搜索错误: {e}")
        
        return results
    
    def download(self, book_info: Dict, save_path: str) -> bool:
        return False


# ============================================
# 从 app.py 导入核心处理函数
# ============================================
def import_graph_core():
    """动态导入 app.py 中的核心函数"""
    import importlib.util
    
    app_path = Path(__file__).parent / "app.py"
    if not app_path.exists():
        print("[错误] 找不到 app.py")
        return None
    
    # 创建一个简化的图谱处理模块
    return GraphProcessor()


class GraphProcessor:
    """图谱处理器 - 简化版，避免导入 Streamlit"""
    
    def __init__(self):
        self.client = None
        self.model = CONFIG["gemini_model"]
    
    def init_client(self, api_key: str):
        """初始化 Gemini 客户端"""
        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
            return True
        except Exception as e:
            print(f"[错误] 初始化 Gemini 失败: {e}")
            return False
    
    def read_file(self, file_path: str) -> str:
        """读取文件内容"""
        ext = Path(file_path).suffix.lower()
        text = ""
        
        try:
            if ext == ".pdf":
                import pypdf
                with open(file_path, 'rb') as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages:
                        text += (page.extract_text() or "") + "\n"
                        
            elif ext == ".epub":
                import ebooklib
                from ebooklib import epub
                from bs4 import BeautifulSoup
                
                book = epub.read_epub(file_path, options={'ignore_ncx': True})
                for item in book.get_items():
                    if item.get_type() == ebooklib.ITEM_DOCUMENT:
                        soup = BeautifulSoup(item.get_content(), "html.parser")
                        text += soup.get_text(separator='\n', strip=True) + "\n"
                        
            elif ext == ".txt":
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                    
            else:
                print(f"[警告] 不支持的文件格式: {ext}")
                
        except Exception as e:
            print(f"[错误] 读取文件失败: {e}")
        
        return text.strip()
    
    def chunk_text(self, text: str, chunk_size: int = 4000) -> List[str]:
        """切分文本"""
        paragraphs = re.split(r'\n\s*\n', text)
        chunks, current = [], ""
        
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            if len(current) + len(p) < chunk_size:
                current += "\n\n" + p if current else p
            else:
                if current:
                    chunks.append(current)
                current = p
        
        if current:
            chunks.append(current)
        
        return chunks or [text[:chunk_size]]
    
    def extract_graph(self, text: str) -> Dict:
        """提取知识图谱"""
        if not self.client:
            return {"entities": [], "events": [], "relations": []}
        
        from google.genai import types
        
        prompt = """你是一个专业的历史政治文献分析专家。请从以下文本中提取实体、事件和关系。

【文本】:
{text}

**提取要求：**
1. 实体：政治人物、地点、组织、文件/著作、概念
2. 事件：会议、冲突、讲话、政策、运动
3. 关系：实体与事件之间的关系

**返回JSON格式：**
{{
  "entities": [{{"id": "PER_姓名", "name": "名字", "type": "PERSON", "alias": []}}],
  "events": [{{"id": "EVT_事件_年份", "name": "事件名", "type": "MEETING", "time_str": "YYYY-MM-DD", "description": "描述", "political_significance": "意义", "risk_level": "SAFE"}}],
  "relations": [{{"source_id": "...", "target_id": "...", "relation": "动词", "details": "说明", "evidence": "证据"}}]
}}
""".format(text=text[:8000])
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"[错误] 图谱提取失败: {e}")
            return {"entities": [], "events": [], "relations": []}
    
    def process_book(self, file_path: str) -> Dict:
        """处理整本书"""
        print(f"\n[处理] {Path(file_path).name}")
        
        # 读取文件
        text = self.read_file(file_path)
        if not text:
            return {"error": "无法读取文件内容"}
        
        print(f"  文本长度: {len(text)} 字符")
        
        # 切分
        chunks = self.chunk_text(text)
        print(f"  切分为 {len(chunks)} 块")
        
        # 提取每块的图谱
        all_entities = {}
        all_events = {}
        all_relations = []
        
        for i, chunk in enumerate(chunks[:20]):  # 限制处理前20块
            print(f"  处理第 {i+1}/{min(len(chunks), 20)} 块...")
            result = self.extract_graph(chunk)
            
            for e in result.get("entities", []):
                if e.get("id") not in all_entities:
                    all_entities[e["id"]] = e
            
            for ev in result.get("events", []):
                if ev.get("id") not in all_events:
                    all_events[ev["id"]] = ev
            
            all_relations.extend(result.get("relations", []))
            
            time.sleep(1)  # 避免 API 限流
        
        # 去重关系
        seen = set()
        unique_relations = []
        for r in all_relations:
            key = f"{r.get('source_id')}|{r.get('relation')}|{r.get('target_id')}"
            if key not in seen:
                seen.add(key)
                unique_relations.append(r)
        
        return {
            "file": Path(file_path).name,
            "text_length": len(text),
            "chunks": len(chunks),
            "entities": list(all_entities.values()),
            "events": list(all_events.values()),
            "relations": unique_relations,
            "processed_at": datetime.now().isoformat()
        }


# ============================================
# Book Hunter 主类
# ============================================
class BookHunter:
    """图书猎手 - 自动搜索、下载、分析"""
    
    def __init__(self, api_key: str = ""):
        self.sources = [
            LibGenSource(),
            # ZLibrarySource(),  # 需要登录
            # AnnaArchiveSource(),  # 需要解析
        ]
        self.processor = GraphProcessor()
        self.processed_db = self._load_processed_db()
        
        # 初始化 Gemini
        api_key = api_key or CONFIG["gemini_api_key"]
        if api_key:
            self.processor.init_client(api_key)
        else:
            print("[警告] 未设置 GEMINI_API_KEY，图谱生成功能不可用")
        
        # 创建目录
        Path(CONFIG["download_dir"]).mkdir(exist_ok=True)
        Path(CONFIG["output_dir"]).mkdir(exist_ok=True)
    
    def _load_processed_db(self) -> Dict:
        """加载已处理书籍数据库"""
        db_path = Path(CONFIG["processed_db"])
        if db_path.exists():
            with open(db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"books": {}}
    
    def _save_processed_db(self):
        """保存已处理书籍数据库"""
        with open(CONFIG["processed_db"], 'w', encoding='utf-8') as f:
            json.dump(self.processed_db, f, ensure_ascii=False, indent=2)
    
    def _get_book_id(self, book_info: Dict) -> str:
        """生成书籍唯一ID"""
        key = f"{book_info.get('title')}_{book_info.get('author')}_{book_info.get('md5', '')}"
        return hashlib.md5(key.encode()).hexdigest()[:12]
    
    def search_books(self, query: str, limit: int = 10) -> List[Dict]:
        """搜索书籍"""
        all_results = []
        
        for source in self.sources:
            results = source.search(query, limit)
            all_results.extend(results)
            
            if len(all_results) >= limit:
                break
        
        return all_results[:limit]
    
    def download_book(self, book_info: Dict) -> Optional[str]:
        """下载书籍"""
        book_id = self._get_book_id(book_info)
        
        # 检查是否已下载
        if book_id in self.processed_db["books"]:
            existing = self.processed_db["books"][book_id]
            if existing.get("downloaded") and Path(existing.get("file_path", "")).exists():
                print(f"[跳过] 已下载: {book_info.get('title')}")
                return existing["file_path"]
        
        # 下载
        ext = book_info.get("extension", "pdf")
        filename = f"{book_id}_{self._safe_filename(book_info.get('title', 'unknown'))}.{ext}"
        save_path = str(Path(CONFIG["download_dir"]) / filename)
        
        for source in self.sources:
            if source.download(book_info, save_path):
                # 记录
                self.processed_db["books"][book_id] = {
                    "title": book_info.get("title"),
                    "author": book_info.get("author"),
                    "downloaded": True,
                    "file_path": save_path,
                    "downloaded_at": datetime.now().isoformat()
                }
                self._save_processed_db()
                return save_path
        
        return None
    
    def _safe_filename(self, name: str) -> str:
        """生成安全的文件名"""
        # 移除非法字符
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        # 截断
        return name[:50]
    
    def process_book(self, file_path: str) -> Dict:
        """处理书籍生成图谱"""
        if not self.processor.client:
            print("[错误] Gemini 未初始化")
            return {}
        
        result = self.processor.process_book(file_path)
        
        # 保存图谱
        if result.get("entities") or result.get("events"):
            output_file = Path(CONFIG["output_dir"]) / f"{Path(file_path).stem}_graph.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"[保存] 图谱已保存到: {output_file}")
            result["output_file"] = str(output_file)
        
        return result
    
    def hunt(self, keywords: List[str] = None, booklist: List[str] = None, authors: List[str] = None):
        """执行狩猎任务"""
        queries = []
        
        if keywords:
            queries.extend(keywords)
        if authors:
            queries.extend([f"author:{a}" for a in authors])
        if booklist:
            queries.extend(booklist)
        
        if not queries:
            print("[错误] 请提供搜索关键词、书名或作者")
            return
        
        print(f"\n{'='*50}")
        print(f"Book Hunter 开始狩猎")
        print(f"查询: {queries}")
        print(f"{'='*50}\n")
        
        all_books = []
        for query in queries:
            books = self.search_books(query, limit=5)
            all_books.extend(books)
            time.sleep(CONFIG["delay_between_downloads"])
        
        print(f"\n共找到 {len(all_books)} 本书\n")
        
        # 下载并处理
        for i, book in enumerate(all_books[:CONFIG["max_books_per_run"]]):
            print(f"\n[{i+1}/{min(len(all_books), CONFIG['max_books_per_run'])}] {book.get('title')}")
            print(f"  作者: {book.get('author')}")
            print(f"  年份: {book.get('year')}")
            
            # 下载
            file_path = self.download_book(book)
            if not file_path:
                print(f"  [失败] 下载失败")
                continue
            
            # 处理
            result = self.process_book(file_path)
            if result:
                print(f"  [完成] 实体: {len(result.get('entities', []))}, 事件: {len(result.get('events', []))}, 关系: {len(result.get('relations', []))}")
            
            time.sleep(CONFIG["delay_between_downloads"])
        
        print(f"\n{'='*50}")
        print(f"狩猎完成!")
        print(f"{'='*50}\n")
    
    def process_local(self, folder: str):
        """处理本地文件夹中的书籍"""
        folder_path = Path(folder)
        if not folder_path.exists():
            print(f"[错误] 文件夹不存在: {folder}")
            return
        
        files = list(folder_path.glob("*.pdf")) + list(folder_path.glob("*.epub")) + list(folder_path.glob("*.txt"))
        print(f"\n找到 {len(files)} 个文件\n")
        
        for i, file_path in enumerate(files):
            print(f"\n[{i+1}/{len(files)}] {file_path.name}")
            result = self.process_book(str(file_path))
            if result:
                print(f"  实体: {len(result.get('entities', []))}, 事件: {len(result.get('events', []))}, 关系: {len(result.get('relations', []))}")


# ============================================
# 命令行入口
# ============================================
def main():
    parser = argparse.ArgumentParser(description="Book Hunter - 自动搜索、下载图书并生成知识图谱")
    parser.add_argument("--keywords", "-k", type=str, help="搜索关键词，逗号分隔")
    parser.add_argument("--booklist", "-b", type=str, help="书名列表文件")
    parser.add_argument("--author", "-a", type=str, help="作者名，逗号分隔")
    parser.add_argument("--local", "-l", type=str, help="处理本地文件夹")
    parser.add_argument("--api-key", type=str, help="Gemini API Key")
    parser.add_argument("--watch", "-w", action="store_true", help="持续监控模式")
    
    args = parser.parse_args()
    
    # 初始化
    hunter = BookHunter(api_key=args.api_key or "")
    
    # 处理本地文件
    if args.local:
        hunter.process_local(args.local)
        return
    
    # 准备查询
    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else None
    authors = [a.strip() for a in args.author.split(",")] if args.author else None
    
    booklist = None
    if args.booklist:
        with open(args.booklist, 'r', encoding='utf-8') as f:
            booklist = [line.strip() for line in f if line.strip()]
    
    if not keywords and not authors and not booklist:
        print("请提供搜索参数:")
        print("  --keywords '将军回忆录,军事历史'")
        print("  --author '粟裕,许世友'")
        print("  --booklist books.txt")
        print("  --local ./my_books/")
        return
    
    # 执行
    if args.watch:
        print("持续监控模式启动 (Ctrl+C 退出)")
        while True:
            hunter.hunt(keywords=keywords, booklist=booklist, authors=authors)
            print(f"\n等待 1 小时后再次执行...\n")
            time.sleep(3600)
    else:
        hunter.hunt(keywords=keywords, booklist=booklist, authors=authors)


if __name__ == "__main__":
    main()
