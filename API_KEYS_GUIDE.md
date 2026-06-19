# 免费搜索工具 API Key 获取指南

## 📋 快速获取清单 x

| 工具 | 免费额度 | 获取链接 | 状态 |
|------|----------|----------|------|
| Tavily | 1000次/月 | https://tavily.com | ⬜ 待获取 |
| Exa | $10额度 | https://dashboard.exa.ai | ⬜ 待获取 |
| Jina Reader | 100万Token | https://jina.ai/reader | ⬜ 待获取 |
| DuckDuckGo | 无限免费 | 无需API Key | ✅ 已配置 |

---

## 1️⃣ Tavily (推荐 - 专为AI Agent优化)

**免费额度**: 1,000次/月，无需绑卡

### 获取步骤:
1. 访问 https://tavily.com
2. 点击 "Start for Free" 注册
3. 支持 Google/GitHub 登录
4. 进入 Dashboard 获取 API Key
5. 复制到 `config.json` 的 `TAVILY_API_KEY`

### 特点:
- 专为 LLM 和 AI Agent 设计
- 实时搜索，支持20+来源
- 93.3% 准确率
- 支持 Python/JS SDK

---

## 2️⃣ Exa (语义搜索)

**免费额度**: $10 免费额度（约2000次搜索）

### 获取步骤:
1. 访问 https://dashboard.exa.ai
2. 使用 Google/GitHub 注册
3. 进入 API Keys 页面
4. 创建新的 API Key
5. 复制到 `config.json` 的 `EXA_API_KEY`

### 特点:
- 语义搜索，比关键词更智能
- 支持代码搜索
- 高质量搜索结果

---

## 3️⃣ Jina Reader (网页内容提取)

**免费额度**: 100万Token + 200 RPM

### 获取步骤:
1. 访问 https://jina.ai/reader
2. 点击 "API Key & Billing"
3. 注册并获取 API Key
4. 复制到 `config.json` 的 `JINA_API_KEY`

### 特点:
- 将任意网页转为 LLM 友好的 Markdown
- 支持 PDF 读取
- 图片自动标注

---

## 4️⃣ DuckDuckGo (完全免费)

**无需 API Key**，已默认配置，开箱即用！

### 特点:
- 完全免费，无限制
- 注重隐私
- 适合基础搜索

---

## 🔧 配置方法

获取 API Key 后，编辑 `/Users/jack/.nanobot/config.json`:

```json
"mcpServers": {
  "tavily": {
    "env": {
      "TAVILY_API_KEY": "tvly-xxxxxxxx"  // 替换这里
    }
  },
  "exa": {
    "env": {
      "EXA_API_KEY": "xxxxxxxx"  // 替换这里
    }
  },
  "jina-reader": {
    "env": {
      "JINA_API_KEY": "xxxxxxxx"  // 替换这里
    }
  }
}
```

---

## 💡 使用建议

| 场景 | 推荐工具 |
|------|----------|
| 日常搜索 | DuckDuckGo (免费无限) |
| AI技术研究 | Tavily (专为AI优化) |
| 代码搜索 | Exa (语义搜索) |
| 网页内容提取 | Jina Reader |

---

## ⚠️ 注意事项

1. **API Key 安全**: 不要提交到 Git 仓库
2. **额度监控**: 定期检查使用量
3. **优先级**: 先用免费的 DuckDuckGo，需要更高质量时用其他工具

---

生成时间: 2025-02-24
