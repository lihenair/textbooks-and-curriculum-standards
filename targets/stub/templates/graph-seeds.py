"""章节图种子。由知识库流水线整体重生成，不要手改。"""

OWNED_LATER = {
{{#each owned_later}}    {{py:chapter_id}}: {{py:ids}},
{{/each}}}

SEED_NODES = (
{{#each seed_nodes}}    ({{py:id}}, {{py:subject}}, {{py:display}}, {{py:chapter_id}}, {{grey}}),
{{/each}})

SEED_EDGES = (
{{#each seed_edges}}    ({{py:src}}, {{py:dst}}, {{py:kind}}),
{{/each}})
