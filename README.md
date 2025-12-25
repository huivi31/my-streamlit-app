<div align="center">

# 🕸️ DeepGraph Pro
### AI-Powered Knowledge Graph Generator
### 基于 Gemini 的智能文档知识图谱生成器

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://deepgraph-huivi.streamlit.app)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Gemini](https://img.shields.io/badge/AI-Google%20Gemini-orange)
![License](https://img.shields.io/badge/License-MIT-green)

<br>

**DeepGraph Pro** 是一款基于 LLM 的可视化分析工具。它利用 Google Gemini 强大的上下文理解能力，从非结构化文档（PDF, DOCX, EPUB）中提取 **SVO（主谓宾）** 三元组，并构建交互式知识图谱，帮助用户快速洞察文本中的实体关系、风险网络和关键路径。

[查看演示 Demo](https://deepgraph-huivi.streamlit.app) · [报告 Bug](https://github.com/huivi31/my-streamlit-app/issues) · [请求功能](https://github.com/huivi31/my-streamlit-app/issues)

</div>

---

## ✨ 核心功能 (Key Features)

* **⚡️ 极速分析 (Flash Speed)**: 集成 `gemini-2.0-flash-exp` 模型，支持超长文本的秒级推理。
* **📄 多格式支持**: 完美解析 `PDF`, `EPUB`, `DOCX`, `TXT` 等多种文档格式。
* **🔍 智能 SVO 提取**: 自动识别实体关系，并进行类型分类（如：HighRisk, Faction, Person, Outcome）。
* **🕸️ 交互式图谱**: 基于 `PyVis` 和 `NetworkX` 构建的物理引擎图谱，支持拖拽、缩放和节点高亮。
* **🔗 实体对齐**: 内置实体消歧算法，自动合并同义词（例如将 "Apple Inc." 和 "Apple" 合并）。
* **📊 自动简报**: 一键生成结构化的 Markdown 文本简报，包含所有关键关系链。
* **☁️ 云端原生**: 专为 Streamlit Community Cloud 优化，无需本地 GPU，开箱即用。

## 🛠️ 技术栈 (Tech Stack)

| 组件 | 技术选型 | 说明 |
| :--- | :--- | :--- |
| **Frontend** | Streamlit | 极简 Python Web UI 框架 |
| **LLM Core** | Google GenAI SDK | 调用 Gemini Flash/Pro 模型 |
| **Graph Engine** | NetworkX | 图论算法与结构计算 |
| **Visualization** | PyVis | 基于 Web 的交互式网络可视化 |
| **Parser** | PyPDF / Docx / EbookLib | 多格式文档解析引擎 |

## 🚀 快速开始 (Quick Start)

### 本地运行 (Local Development)

1.  **克隆仓库**
    ```bash
    git clone [https://github.com/huivi31/my-streamlit-app.git](https://github.com/huivi31/my-streamlit-app.git)
    cd my-streamlit-app
    ```

2.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

3.  **配置 API Key**
    * 你需要一个 Google Gemini API Key。
    * 运行应用时在侧边栏输入，或设置环境变量 `GOOGLE_API_KEY`。

4.  **启动应用**
    ```bash
    streamlit run app.py
    ```

## ☁️ 部署 (Deployment)

本项目已针对 **Streamlit Community Cloud** 进行优化，可实现自动化 CI/CD 部署。

1.  Fork 本仓库到你的 GitHub。
2.  登录 [Streamlit Cloud](https://share.streamlit.io)。
3.  点击 **"New app"**。
4.  选择你的仓库、分支 (`main`) 和主文件 (`app.py`)。
5.  点击 **"Deploy"**，即可获得永久免费的 HTTPS 访问地址。

## 📸 截图 (Screenshots)

> *请在此处上传一张你的应用运行截图，命名为 screenshot.png 并放在仓库根目录*
> ![App Screenshot](screenshot.png)

## 🤝 贡献 (Contributing)

欢迎提交 Pull Request 或 Issue！

1.  Fork 本仓库
2.  新建 Feat_xxx 分支
3.  提交代码
4.  新建 Pull Request

## 📄 开源协议 (License)

本项目采用 [MIT License](LICENSE) 开源协议。

---

<div align="center">
    Designed with ❤️ by Huivi31
</div>
