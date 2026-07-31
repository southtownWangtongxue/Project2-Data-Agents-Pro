"""
文本摘要 Skill — 实际执行脚本
基于 LLM 对长文本生成中文摘要
"""
from app.core.llm import get_llm, get_model_name
from app.utils.log_utils import log


async def summarize_text(text: str, max_length: int = 200) -> dict:
    """
    对给定文本生成中文摘要。

    参数:
        text: 待摘要文本
        max_length: 摘要最大字数

    返回:
        {status, summary}
    """
    if not text or not text.strip():
        return {"status": "error", "message": "摘要内容为空"}

    client = get_llm()
    prompt = (
        f"请用不超过 {max_length} 字的中文，概括以下内容的 3 个以内核心要点，"
        f"直接输出要点，不要解释：\n\n{text[:4000]}"
    )
    try:
        resp = await client.chat.completions.create(
            model=get_model_name(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        summary = (resp.choices[0].message.content or "").strip()
        log.info("[Summarizer] 摘要生成完成, %d 字 -> %d 字", len(text), len(summary))
        return {"status": "success", "summary": summary}
    except Exception as exc:
        log.error(f"[Summarizer] 摘要生成失败: {exc}")
        return {"status": "error", "message": f"摘要生成失败: {str(exc)}"}
