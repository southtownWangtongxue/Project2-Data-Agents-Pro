"""
ModeRouter — 根据 mode 参数动态加载对应的 LangGraph StateGraph。

支持 4 种工作模式:
  - data:  数据分析（现有 13 节点 Plan-and-Execute + ReAct）
  - report: 研究报告（RAG 检索 + LLM 报告生成）
  - doc:    文档智读（文档上传 + 向量化 + RAG 问答）
  - task:   通用任务（deepagents 通用 Agent，阶段 10 实现）

用法:
    from app.graph.mode_router import get_graph as get_graph_by_mode
    graph = get_graph_by_mode("report")
    async for event in graph.astream(state, config):
        ...
"""
from typing import Callable
from langgraph.graph import StateGraph
from app.utils.log_utils import log


MODE_REGISTRY: dict[str, Callable[[], StateGraph]] = {}


def register_mode(name: str):
    """装饰器：注册一个工作流模式到 MODE_REGISTRY。

    用法:
        @register_mode("report")
        def get_report_workflow() -> StateGraph:
            ...
    """
    def decorator(fn: Callable[[], StateGraph]):
        MODE_REGISTRY[name] = fn
        log.info(f"[ModeRouter] 注册模式: {name}")
        return fn
    return decorator


def get_graph(mode: str = "data") -> StateGraph:
    """
    根据 mode 参数获取编译后的 StateGraph 实例。
    """
    _ensure_workflows_loaded()

    if mode not in MODE_REGISTRY:
        log.warning(f"[ModeRouter] 未注册模式 '{mode}'，回退到 'data'")
        mode = "data"

    builder: StateGraph = MODE_REGISTRY[mode]()
    from app.graph.workflow import get_checkpointer
    return builder.compile(checkpointer=get_checkpointer())


def _ensure_workflows_loaded():
    """确保所有工作流模块已导入（触发 @register_mode 装饰器注册）。"""
    if not MODE_REGISTRY:
        import app.graph.workflow          # noqa: F401 — data 模式
        import app.graph.report_workflow   # noqa: F401 — report 模式
        import app.graph.doc_workflow     # noqa: F401 — doc 模式
        import app.graph.task_workflow   # noqa: F401 — task 模式
