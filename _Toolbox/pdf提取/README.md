# pdf提取

PDF 页面体检、全文提取、指定页提图。三个动作一个工具。

## 用途

- **survey**：逐页统计字符数和图片数，判断这份 PDF 是文字型还是扫描件
- **text**：提取全文到 txt，按页分隔，方便后续 grep 定位
- **images**：把指定页渲染成 PNG，可以裁掉顶部标题栏（很多 PPT 转的 PDF 顶部有装饰条）

## 输入

任意 PDF。路径从命令行传，不写死在代码里。

## 输出

- `text`：`<out>/全文.txt`（可用 `--name` 改名）
- `images`：`<out>/p04.png` 这样按页码命名（可用 `--prefix` 改前缀）

## 依赖

```
pip install pymupdf
```

## 示例

```powershell
# 1. 先体检，判断文字型还是扫描件
python pdf_extract.py survey --pdf 输入资料/某任务/文档.pdf

# 2. 文字型就直接提全文
python pdf_extract.py text --pdf 输入资料/某任务/文档.pdf --out _scratch/某任务-处理

# 3. 提第 4、5、8 页的图，裁掉顶部 78 磅
python pdf_extract.py images --pdf 输入资料/某任务/文档.pdf --pages 4,5,8 `
    --out 输出结果/某任务/图 --clip-top 78
```

## 什么时候用

| 场景 | 用哪个 |
| :--- | :--- |
| 拿到陌生 PDF，不知道能不能提文字 | `survey` |
| 要去里面找几个知识点 | `text` 后 grep 定位 |
| 要给文档配图 | `images` |
| 扫描件（survey 判定全是图） | 本工具帮不了，需要 OCR |

## 来源

由「接地熔断判别」项目里的 `extract.py` 和 `extract_images.py` 合并改造而成。
原脚本写死了 PDF 路径和 11 个页码，无法复用；现在全部改成参数。

## 已验证

2026-11-22：31 页 / 4.6 MB 的真实 PDF，survey 正确判定为文字型；text 提取正常；images 按页出图并裁掉标题栏。
