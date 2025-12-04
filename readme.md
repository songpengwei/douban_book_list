## Douban 想读抓取脚本

### 依赖
- Python 3.8+
- `requests`、`beautifulsoup4`：`pip install requests beautifulsoup4`

### 用法
```bash
python fetch_douban_wish.py <douban_user_id> --output <file>
# 示例
python fetch_douban_wish.py qtmuniao --output qtmuniao_wish.json
```

### 输出
- JSON 数组，每本书包含：书名、豆瓣链接、封面、作者、出版社、出版时间、评分、评分人数、简介（如果能抓到）、原始出版信息、书目 ID、标记时间。
- 默认保存为 `douban_wish_<user_id>.json`，可用 `--max-pages` 限制抓取页数。

## 将 JSON 转为 Markdown + 下载封面

```bash
python build_markdown_from_json.py qtmuniao_wish.json --output books.md --columns 3 --img-dir img
```

参数：
- `--columns`：表格每行展示的列数，默认 3
- `--img-dir`：封面保存目录，默认 `img`
- 配色：`--primary-color`、`--bg-color`、`--card-bg`、`--text-color`、`--muted-color`
- `--skip-download`：跳过下载封面（不会回落到远程 URL，表格会显示占位图）

说明：
- 下载时自动带 Referer + 伪装头并随机延迟，多次重试；失败会列出未下载的书目。
- 表格封面只使用本地图片路径，缺失时显示占位块。
- 简介放在卡片底部，若缺失则使用原始出版信息。
