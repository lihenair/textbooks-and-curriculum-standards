"""章节图种子。非灰节点（grey=0）的 id、显示名、章号以 references/nodes/ 的 pipeline 块为唯一真源，由 scripts/canon_sync.py 对账。灰节点（grey=1）只在这里，用来做章末预告。"""

OWNED_LATER = {
{{#each owned_later}}    {{py:chapter_id}}: {{py:ids}},
{{/each}}}

SEED_NODES = (
{{#each seed_nodes}}    ({{py:id}}, {{py:subject}}, {{py:display}}, {{py:chapter_id}}, {{grey}}),
{{/each}})

SEED_EDGES = (
{{#each seed_edges}}    ({{py:src}}, {{py:dst}}, {{py:kind}}),
{{/each}})
