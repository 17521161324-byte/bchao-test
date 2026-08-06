"""可观测 ASR 转化流水线包。

将一次性转化引擎重构为可逐步骤执行、可查看每步输入/输出/规则命中/状态变化的
流水线。入口为 orchestrator.run_pipeline()，兼容旧 run_conversion()。
"""
