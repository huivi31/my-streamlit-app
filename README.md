# 📖 解书客

### 雪山千古冷，独照峨眉峰。

**解书客** 是基于 LLM 的智能文献解析与知识图谱生成工具，支持自动识别文档类型并选择最优抽取策略。

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🔍 **智能分类** | 自动识别6种文档类型（政治敏感/法规/叙事/舆情/经济/通用） |
| 📝 **动态模板** | 每种类型使用专门设计的 Prompt 模板 |
| 📄 **语义分块** | 按段落边界分块，保持语义完整性 |
| 🔗 **实体消歧** | LLM 自动识别并合并同一实体的不同表述 |
| 🎨 **海水配色** | Ocean Teal 渐变主题，护眼舒适 |
| 📜 **公文字体** | 仿宋正文、楷体引用、标题用小标宋 |

## 🚀 快速开始

### 本地运行

```bash
# 克隆仓库
git clone https://github.com/huivi31/my-streamlit-app.git
cd my-streamlit-app

# 安装依赖
pip install -r requirements.txt

# 启动应用
streamlit run app.py
```

### 配置

1. 获取 [Google Gemini API Key](https://ai.google.dev/)
2. 在侧边栏输入 API Key
3. 上传文档开始分析

## 📋 支持的文档类型

| 类型 | 适用场景 | Prompt 重点 |
|------|----------|------------|
| `political_sensitive` | 政治/历史敏感内容 | 群体事件、维稳、高层斗争 |
| `regulatory` | 法规/政策文件 | 条款、处罚措施、权利义务 |
| `narrative` | 历史叙事/传记 | 时间线、人物关系、因果链 |
| `opinion` | 舆情/评论 | 情感倾向、立场表达、反讽识别 |
| `economic` | 经济/商业 | 企业关系、交易行为、市场事件 |
| `general` | 通用内容 | 标准 SVO 抽取 |

## 📄 支持的文件格式

- PDF
- EPUB
- DOCX
- TXT

## ☁️ 在线体验

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/huivi31/my-streamlit-app/main/app.py)

## 📄 开源协议

MIT License
