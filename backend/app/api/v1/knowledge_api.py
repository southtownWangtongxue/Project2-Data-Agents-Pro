"""
知识库管理 API — 文件上传 / 列表 / 搜索 / 删除
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.api.v1.auth import get_current_user
from app.rag.knowledge import upload_document
from app.rag.retriever import search_similar, get_collection_info
import uuid

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/upload")
async def kb_upload(file: UploadFile = File(...), user=Depends(get_current_user)):
    """上传文档到知识库：解析 → 切分 → 向量化 → 存入 Milvus"""
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("pdf", "docx", "md", "txt", "py", "json", "csv"):
        raise HTTPException(400, f"不支持的文件格式: .{ext}")
    try:
        content = await file.read()
        result = await upload_document(content, file.filename, collection_name=f"kb_{user['user_name']}")
        ok = result.get("status") == "success"
        if not ok:
            # 入库未成功（如文本为空、向量化或 Milvus 异常），返回 4xx 明确告知前端
            raise HTTPException(400, result.get("message", "文档处理失败"))
        return {"ok": True, "doc_id": result.get("doc_id", str(uuid.uuid4())), "chunks": result.get("chunks", 0)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"处理失败: {str(e)}")


@router.get("/list")
async def kb_list(user=Depends(get_current_user)):
    """列出当前用户的知识库文档"""
    try:
        info = await get_collection_info(f"kb_{user['user_name']}")
        return {"documents": info if isinstance(info, list) else []}
    except Exception:
        return {"documents": []}


@router.post("/search")
async def kb_search(query: str, top_k: int = 5, user=Depends(get_current_user)):
    """检索知识库中与 query 最相关的文档片段"""
    try:
        results = await search_similar(query, collection_name=f"kb_{user['user_name']}", top_k=top_k)
        return {"results": results}
    except Exception as e:
        raise HTTPException(500, f"检索失败: {str(e)}")



