"""
知识库管理
处理文档上传、解析、入库的完整流程
"""
import io
import logging
from typing import Optional

from app.core.config import settings
from app.rag.embeddings import embed_and_store
from app.rag.retriever import get_collection_info

logger = logging.getLogger(__name__)


# ── 文档上传 ────────────────────────────────────────────────────────────


async def upload_document(
    file_content: bytes,
    filename: str,
    collection_name: Optional[str] = None,
) -> dict:
    """
    解析上传文件内容并存入知识库。

    支持的文件格式：
    - .txt / .md / .py / .json 等纯文本文件 —— 直接解码为文本
    - .pdf —— 通过 PyPDF2 或 pdfplumber 提取文本（需安装对应库）

    流程：
    1. 根据文件扩展名选择解析器，提取纯文本
    2. 调用 chunk → embed → store 流水线将文本存入 Milvus
    3. 返回处理结果摘要

    参数:
        file_content: 文件的原始字节内容
        filename:     文件名（用于通过扩展名判断文件类型）
        collection_name: 目标 Milvus collection 名称，默认使用配置值

    返回:
        dict 包含:
            - status (str):   "success" 或 "error"
            - chunks (int):   成功入库的文档片段数量
            - filename (str): 文件名
            - message (str):  处理结果描述
    """
    used_collection = collection_name or settings.MILVUS_COLLECTION_NAME

    # 1. 解析文件提取文本
    text = _extract_text(file_content, filename)
    if not text or not text.strip():
        return {
            "status": "error",
            "chunks": 0,
            "filename": filename,
            "message": "无法从文件中提取文本内容，文件可能为空或格式不支持",
        }

    logger.info("文件 '%s' 解析成功，提取文本长度=%d 字符", filename, len(text))

    # 2. 入库（chunk → embed → store）
    chunks_count = await embed_and_store([text], used_collection)

    if chunks_count == 0:
        return {
            "status": "error",
            "chunks": 0,
            "filename": filename,
            "message": "文本向量化或 Milvus 入库失败，请检查 Embedding API 和 Milvus 服务是否正常",
        }

    return {
        "status": "success",
        "chunks": chunks_count,
        "filename": filename,
        "message": f"成功入库 {chunks_count} 个文档片段",
    }


# ── 文档列表 ────────────────────────────────────────────────────────────


async def list_documents(collection_name: Optional[str] = None) -> list[dict]:
    """
    列出知识库中已有的文档摘要信息。

    参数:
        collection_name: collection 名称，默认使用配置值

    返回:
        文档摘要列表，每个元素包含 collection 状态和文档片段数量等信息。
        当前实现返回单个 collection 的统计信息。
    """
    used_collection = collection_name or settings.MILVUS_COLLECTION_NAME
    info = await get_collection_info(used_collection)
    return [info]


# ── 内部文本提取工具 ─────────────────────────────────────────────────────

# 纯文本文件扩展名集合
_TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "rst",
    "py", "js", "ts", "jsx", "tsx", "java", "go", "rs", "c", "cpp", "h",
    "sql", "json", "xml", "yaml", "yml", "toml", "ini", "cfg", "csv",
    "html", "css", "scss", "less",
}


def _extract_text(file_content: bytes, filename: str) -> str:
    """
    根据文件名扩展名选择合适的文本提取器。

    参数:
        file_content: 文件字节内容
        filename: 文件名

    返回:
        提取的纯文本字符串；无法提取时返回空字符串。
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # 纯文本类文件（包括代码、配置、标记语言等）
    if ext in _TEXT_EXTENSIONS:
        return _decode_text(file_content)

    # PDF 文件
    if ext == "pdf":
        return _extract_pdf_text(file_content)

    # 未知类型，尝试按 UTF-8 解码
    return _decode_text(file_content)


def _decode_text(file_content: bytes) -> str:
    """
    尝试将字节内容解码为文本，依次尝试 UTF-8、GBK，最后使用 replacement 模式。

    参数:
        file_content: 文件字节内容

    返回:
        解码后的文本字符串。
    """
    for encoding in ("utf-8", "gbk"):
        try:
            return file_content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_content.decode("utf-8", errors="replace")


def _extract_pdf_text(file_content: bytes) -> str:
    """
    从 PDF 字节内容中提取纯文本。

    依次尝试 PyPDF2 和 pdfplumber 两个库，如果都未安装则返回空字符串。

    参数:
        file_content: PDF 文件的原始字节内容

    返回:
        提取的文本内容，各页之间以双换行分隔。
    """
    # 尝试 PyPDF2
    try:
        from PyPDF2 import PdfReader  # type: ignore[import-untyped]

        reader = PdfReader(io.BytesIO(file_content))
        texts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                texts.append(page_text)
        extracted = "\n\n".join(texts)
        if extracted.strip():
            return extracted
        logger.debug("PyPDF2 提取文本为空，尝试下一个库")
    except ImportError:
        logger.debug("PyPDF2 未安装")
    except Exception as e:
        logger.debug(f"PyPDF2 解析失败: {e}")

    # 尝试 pdfplumber（备用）
    try:
        import pdfplumber  # type: ignore[import-untyped]

        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            texts = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    texts.append(page_text)
            extracted = "\n\n".join(texts)
            if extracted.strip():
                return extracted
            logger.debug("pdfplumber 提取文本为空")
    except ImportError:
        logger.warning("PyPDF2 和 pdfplumber 均未安装，无法解析 PDF 文件。请安装: pip install PyPDF2")
    except Exception as e:
        logger.warning(f"pdfplumber 解析失败: {e}")

    return ""
