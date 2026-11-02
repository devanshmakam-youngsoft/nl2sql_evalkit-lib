"""Every prompt the question writer uses, one file each, each exporting one named variable."""
from nl2sql_evalkit.prompts.testcase_generator.aggregate import aggregate_prompt
from nl2sql_evalkit.prompts.testcase_generator.common_rules import common_rules
from nl2sql_evalkit.prompts.testcase_generator.followup import followup_prompt
from nl2sql_evalkit.prompts.testcase_generator.join import join_prompt
from nl2sql_evalkit.prompts.testcase_generator.nested import nested_prompt
from nl2sql_evalkit.prompts.testcase_generator.retry import retry_instruction
from nl2sql_evalkit.prompts.testcase_generator.simple import simple_prompt
from nl2sql_evalkit.prompts.testcase_generator.unsafe import unsafe_prompt
from nl2sql_evalkit.prompts.testcase_generator.vague import vague_prompt

CATEGORY_PROMPTS = {
    "simple": simple_prompt,
    "join": join_prompt,
    "aggregate": aggregate_prompt,
    "nested": nested_prompt,
    "followup": followup_prompt,
    "vague": vague_prompt,
    "unsafe": unsafe_prompt,
}

__all__ = [
    "CATEGORY_PROMPTS", "aggregate_prompt", "common_rules", "followup_prompt", "join_prompt", "nested_prompt",
    "retry_instruction", "simple_prompt", "unsafe_prompt", "vague_prompt",
]
