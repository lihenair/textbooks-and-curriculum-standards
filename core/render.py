"""小模板：{{name}}、{{py:name}}、{{#each}}、{{#if}}。"""

from __future__ import annotations


class RenderError(ValueError):
    pass


def render(template: str, context: dict) -> str:
    text, index = _render(template, context, 0)
    if index != len(template):
        raise RenderError("模板没有消费完")
    return text


def _render(template: str, context: dict, index: int) -> tuple[str, int]:
    out: list[str] = []
    while index < len(template):
        if template.startswith("{{#each ", index):
            block, index = _block(template, index, "each")
            name = block[0]
            body = block[1]
            items = context.get(name)
            if not isinstance(items, list):
                raise RenderError(f"{name} 不是列表，不能 each")
            for item_index, item in enumerate(items, 1):
                if not isinstance(item, dict):
                    raise RenderError(f"{name} 的元素必须是映射")
                scope = dict(context)
                scope.update(item)
                scope["index"] = item_index
                rendered, _ = _render(body, scope, 0)
                out.append(rendered)
            continue
        if template.startswith("{{#if ", index):
            block, index = _block(template, index, "if")
            name, body = block
            if context.get(name):
                rendered, _ = _render(body, context, 0)
                out.append(rendered)
            continue
        if template.startswith("{{/", index):
            return "".join(out), index
        if template.startswith("{{", index):
            end = template.find("}}", index)
            if end < 0:
                raise RenderError("模板变量没有闭合")
            token = template[index + 2 : end].strip()
            out.append(_value(token, context))
            index = end + 2
            continue
        out.append(template[index])
        index += 1
    return "".join(out), index


def _block(template: str, index: int, kind: str) -> tuple[tuple[str, str], int]:
    header_end = template.find("}}", index)
    if header_end < 0:
        raise RenderError(f"{kind} 没有闭合")
    name = template[index + len("{{#" + kind) + 1 : header_end].strip()
    body_start = header_end + 2
    depth = 1
    cursor = body_start
    open_token = "{{#" + kind
    close_token = "{{/" + kind + "}}"
    while cursor < len(template):
        next_open = template.find(open_token, cursor)
        next_close = template.find(close_token, cursor)
        if next_close < 0:
            raise RenderError(f"{kind} 缺少结束标签")
        if next_open >= 0 and next_open < next_close:
            depth += 1
            cursor = next_open + len(open_token)
            continue
        depth -= 1
        if depth == 0:
            body = template[body_start:next_close]
            return (name, body), next_close + len(close_token)
        cursor = next_close + len(close_token)
    raise RenderError(f"{kind} 缺少结束标签")


def _value(token: str, context: dict) -> str:
    as_python = token.startswith("py:")
    key = token[3:] if as_python else token
    if key not in context:
        raise RenderError(f"模板变量不存在：{key}")
    value = context[key]
    if as_python:
        return repr(value)
    return str(value)
