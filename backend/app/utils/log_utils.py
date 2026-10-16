import re
import sys, os
from loguru import logger

# 获得当前项目的绝对路径
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_dir = os.path.join(root_dir, "logs")  # 存放项目日志目录的绝对路径

if not os.path.exists(log_dir):  # 如果日志目录不存在则创建
    os.mkdir(log_dir)

# Trace < Debug < Info < Success < Warning < Error < Critical


class MyLogger:
    def __init__(self):
        self.logger = logger  # 写日志的对象
        # 清空所有设置
        self.logger.remove()
        # 添加控制台输出的格式,sys.stdout为输出到屏幕;关于这些配置还需要自定义请移步官网查看相关参数
        self.logger.add(sys.stdout, level='DEBUG',
                        format="<green>{time:YYYYMMDD HH:mm:ss}</green> | "  # 颜色>时间
                               "{process.name} | "  # 进程名
                               "{thread.name} | "  # 线程名
                               "<cyan>{module}</cyan>.<cyan>{function}</cyan>"  # 模块名.方法名
                               ":<cyan>{line}</cyan> | "  # 行号
                               "<level>{level}</level>: "  # 等级
                               "<level>{message}</level>",  # 日志内容
                        )

    def get_logger(self):
        return self.logger


# printf 风格占位符(%s/%d/%.2f…);%% 转义由 % 格式化语义自然处理
_PRINTF_TOKEN = re.compile(r"%\.?\d*[sdiouxXeEfgG]")


class DualStyleLogger:
    """printf/{} 双风格日志门面。

    历史包袱:全库大量调用按 stdlib logging 习惯写 printf 风格
    (log.warning("x %s", val)),而 loguru 只做 str.format —— 值被静默
    丢弃,只打印字面 %s([SqlGate] 安全审计决策、[Shadow] 失败原因均中招,
    2026-10-16 排查 nemotron 补采失败时实测异常详情完全不可见)。

    本门面按占位符形态分流,一处修复全部既有调用点,两种写法都正确:
    - 含 {} 占位 → loguru 原生 str.format 路径,参数原样透传,行为不变;
    - 含 printf 占位且无 {} → % 格式化后以成品文本调用(参数被消费,
      避免格式化结果里值本身含大括号时被 loguru 二次解析);
    - 参数数不匹配等一切异常退回原样,绝不在日志层抛错。
    未列出的方法/属性经 __getattr__ 透传内层 loguru logger。
    """

    def __init__(self, inner):
        self._inner = inner

    def _emit(self, method, message: str, args: tuple) -> None:
        """printf 分支消费参数后传成品文本;其余原样透传给 loguru。"""
        if args and "{" not in message and _PRINTF_TOKEN.search(message):
            try:
                method(message % args)
                return
            except (TypeError, ValueError):
                pass
        method(message, *args)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def trace(self, message, *args):
        self._emit(self._inner.trace, message, args)

    def debug(self, message, *args):
        self._emit(self._inner.debug, message, args)

    def info(self, message, *args):
        self._emit(self._inner.info, message, args)

    def success(self, message, *args):
        self._emit(self._inner.success, message, args)

    def warning(self, message, *args):
        self._emit(self._inner.warning, message, args)

    def error(self, message, *args):
        self._emit(self._inner.error, message, args)

    def critical(self, message, *args):
        self._emit(self._inner.critical, message, args)

    def exception(self, message, *args):
        self._emit(self._inner.exception, message, args)


log = DualStyleLogger(MyLogger().get_logger())

if __name__ == '__main__':
    # log.debug("This is a debug message.")
    # log.info("This is an info message.")

    log.info("User: {}, Age: {}", "Alice", 25)  # loguru {} 风格
    log.info("printf 风格: %s / %d", "Alice", 25)  # 双风格都应正确输出

    # log.warning('这是一个警告')
    # log.trace('xxxx')
    print('str.pdf'['str.pdf'.rindex('.'):])
    # @log.catch  # 整个函数自动加上try， catch。自动捕获异常，并且自动用日志打印
    def test():
        try:
            print(3/0)
        except ZeroDivisionError as e:
            # log.error(e)
            log.exception(e)  # 以后常用
