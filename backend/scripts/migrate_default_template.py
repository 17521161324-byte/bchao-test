"""
迁移: 更新默认提示词模版,使用英文 JSON 键名 (与前端展示一致)

背景: 旧模版使用中文描述字段,导致 LLM 返回中文 JSON 键名,
      前端展示代码使用英文键名,导致数据无法显示。
"""
import asyncio
from sqlalchemy import text
from app.database import engine

NEW_DEFAULT_CONTENT = """# 角色

你是一名辅助生殖 B 超检查信息结构化专家。

# 任务

请根据以下 ASR 转写文本,提取本次 B 超检查中的结构化字段,并以 JSON 格式返回。

# ASR 转写文本

{transcript}

# 输出要求

请只返回 JSON,不要返回其他任何解释文字。

# JSON 字段说明

- right_follicle_total: 右侧卵泡总数(整数)
- left_follicle_total: 左侧卵泡总数(整数)
- right_follicles: 右侧卵泡列表,每项为 {"size": 数值, "count": 整数}
- left_follicles: 左侧卵泡列表,每项为 {"size": 数值, "count": 整数}
- endometrium_thickness: 内膜厚度(数值,mm)
- endometrium_type: 内膜类型(A/B/C/A-B 等)
- right_ovary_length: 右卵巢长度(数值,mm)
- right_ovary_width: 右卵巢宽度(数值,mm)
- left_ovary_length: 左卵巢长度(数值,mm)
- left_ovary_width: 左卵巢宽度(数值,mm)
- remark: 备注/总结(文本)

# 返回格式示例

```json
{
  "right_follicle_total": 10,
  "left_follicle_total": 6,
  "right_follicles": [
    {"size": 17.5, "count": 1},
    {"size": 15.0, "count": 1}
  ],
  "left_follicles": [
    {"size": 14.3, "count": 1}
  ],
  "endometrium_thickness": 11.7,
  "endometrium_type": "A",
  "right_ovary_length": 31,
  "right_ovary_width": 26,
  "left_ovary_length": 28,
  "left_ovary_width": 27,
  "remark": "未见明显异常"
}
```"""


async def main():
    async with engine.begin() as conn:
        # 只更新默认模版 (id=1 或 is_default=true)
        result = await conn.execute(
            text(
                "UPDATE prompt_templates "
                "SET content = :content, updated_at = CURRENT_TIMESTAMP "
                "WHERE is_default = 1"
            ),
            {"content": NEW_DEFAULT_CONTENT},
        )
        print(f"[ok] 更新了 {result.rowcount} 条默认模版")

        # 同时更新那些内容明显是中文键名的模版 (包含 '内膜' 但没 'right_follicle_total')
        result2 = await conn.execute(
            text(
                "UPDATE prompt_templates "
                "SET is_default = 0 "
                "WHERE is_default = 1 AND id <> 1"
            ),
        )
        if result2.rowcount:
            print(f"[info] 清除了 {result2.rowcount} 条重复默认标记")


if __name__ == "__main__":
    asyncio.run(main())
