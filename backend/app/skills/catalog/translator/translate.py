"""
翻译 Skill — 实际执行脚本
基于 LLM 将文本翻译为目标语言
"""
from app.core.llm import get_llm, get_model_name
from app.utils.log_utils import log


async def translate_text(text: str, target_lang: str = "en") -> dict:
    """
    将文本翻译为目标语言。

    参数:
        text: 待翻译文本
        target_lang: 目标语言（如 "en" / "中文" / "日语"）

    返回:
        {status, translation}
    """
    if not text or not text.strip():
        return {"status": "error", "message": "翻译内容为空"}

    client = get_llm()
    prompt = f"请将以下内容翻译为{target_lang}，只返回译文本身，不要添加任何解释或引号：\n\n{text[:4000]}"
    try:
        resp = await client.chat.completions.create(
            model=get_model_name(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        translation = (resp.choices[0].message.content or "").strip()
        log.info("[Translator] 翻译完成 -> %s", target_lang)
        return {"status": "success", "translation": translation}
    except Exception as exc:
        log.error(f"[Translator] 翻译失败: {exc}")
        return {"status": "error", "message": f"翻译失败: {str(exc)}"}
