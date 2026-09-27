学生问{{book}}第{{chapter_no_zh}}章的知识图谱时，从「整章图」那一行起原样输出，不要改节点、边和配色。

整章图：{{book}}第{{chapter_no_zh}}章

```mermaid
flowchart TD
  classDef concept fill:#E8F1FF,stroke:#3B6FB6,color:#1A1A1A
  classDef skill fill:#E7F6EE,stroke:#2E7D4F,color:#1A1A1A
  classDef experiment fill:#FFF4E5,stroke:#C47B17,color:#1A1A1A
  classDef later fill:#F4F4F5,stroke:#71717A,color:#1A1A1A
  subgraph ch["第{{chapter_no_zh}}章 {{chapter_title}}"]
{{#each sections}}    subgraph s{{index}}["{{title}}"]
{{#each nodes}}      {{id}}["{{graph_label}}"]:::{{type}}
{{/each}}    end
{{/each}}  end
{{#each later}}  {{id}}["{{display}}"]:::later
{{/each}}{{#each solid_edges}}  {{src}} -->|{{kind}}| {{dst}}
{{/each}}{{#each combo_edges}}  {{src}} -.->|{{kind}}| {{#if dst_cross}}{{dst}}["{{dst_label}}"]:::later{{/if}}{{#if dst_in_chapter}}{{dst}}{{/if}}
{{/each}}```

图例：蓝=概念，绿=技能，橙=实验，灰=后续章节。实线=直接前置或同章衔接，虚线=常考组合。

{{entry_question}}
