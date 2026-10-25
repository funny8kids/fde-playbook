#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Obsidian 版《FDE 全书》同步成 GitHub 可直接渲染的版本。

用法：
    python tools/build.py --src "I:/Obsdian-Files/konwledege/FDE全书" --out .

做四件事：
1. 复制 .md 与 附件/*.svg
2. [[双链]] -> 相对路径 Markdown 链接（含 #锚点，按 GitHub slug 规则生成）
3. 去掉 YAML frontmatter
4. Obsidian callout -> GitHub alert；可折叠块（- / +）-> <details>

不覆盖 README.md / LICENSE / .gitignore / .gitattributes / tools/。
"""
import argparse
import glob
import os
import re
import shutil

ALERT = {
    "abstract": "NOTE", "info": "NOTE", "note": "NOTE", "tip": "TIP", "success": "TIP",
    "important": "IMPORTANT", "warning": "WARNING", "danger": "CAUTION", "caution": "CAUTION",
    "question": "NOTE", "example": "NOTE", "quote": "NOTE", "failure": "CAUTION",
    "bug": "WARNING", "todo": "NOTE",
}
CALL = re.compile(r"^>\s*\[!([a-zA-Z]+)\]([-+]?)\s*(.*)$")
WIKI = re.compile(r"\[\[([^\]\|]+?)(\|([^\]]+))?\]\]")
FM = re.compile(r"^---\r?\n.*?\r?\n---\r?\n+", re.S)
KEEP = {"README.md", "LICENSE", ".gitignore", ".gitattributes"}


def slug(text):
    """近似 GitHub 的标题锚点规则：小写、去掉 ASCII 标点、空格转连字符。"""
    text = text.strip().lower()
    text = re.sub(r"[\\'!\"#$%&()*+,./:;<=>?@\[\]^`{|}~]", "", text)
    return text.replace(" ", "-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Obsidian 版全书目录")
    ap.add_argument("--out", default=".", help="输出目录（默认当前目录）")
    args = ap.parse_args()
    src, out = os.path.abspath(args.src), os.path.abspath(args.out)

    # 1) 复制
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        rel = os.path.relpath(root, src)
        dst_dir = out if rel == "." else os.path.join(out, rel)
        os.makedirs(dst_dir, exist_ok=True)
        for f in files:
            if f.lower() in {k.lower() for k in KEEP}:
                continue
            shutil.copy2(os.path.join(root, f), os.path.join(dst_dir, f))

    # 2) 建立 文件名 -> 路径 映射与标题锚点表
    files = {}
    for p in glob.glob(os.path.join(out, "**", "*.md"), recursive=True):
        files[os.path.basename(p)[:-3]] = p
    slugs = {}
    for b, p in files.items():
        t = open(p, encoding="utf-8").read()
        slugs[b] = [slug(h) for h in re.findall(r"(?m)^#{1,6}\s+(.+)$", t)]

    def link_conv(path):
        here = os.path.dirname(path)

        def rep(m):
            target, alias = m.group(1).strip(), m.group(3)
            anchor = ""
            if "#" in target:
                target, anchor = [x.strip() for x in target.split("#", 1)]
            if target not in files:
                return m.group(0)
            dest = files[target]
            if anchor:
                s = slug(anchor)
                if s not in slugs.get(target, []):
                    cand = [x for x in slugs.get(target, []) if x.startswith(s[:6])]
                    s = cand[0] if cand else s
                dest = dest + "#" + s
            rel = os.path.relpath(dest, here).replace("\\", "/")
            return "[%s](%s)" % (alias if alias else target, rel)

        return rep

    # 3) 逐文件处理
    total_alerts = total_details = 0
    for b, p in files.items():
        if os.path.basename(p).lower() in {k.lower() for k in KEEP}:
            continue
        text = open(p, encoding="utf-8").read()
        text = FM.sub("", text, count=1)
        lines = text.split("\n")
        conv = link_conv(p)
        out_lines, i, infence = [], 0, False
        while i < len(lines):
            line = lines[i]
            if line.strip().startswith("```"):
                infence = not infence
                out_lines.append(line)
                i += 1
                continue
            if infence:
                out_lines.append(line)
                i += 1
                continue
            m = CALL.match(line)
            if m:
                kind, mark, title = m.group(1).lower(), m.group(2), m.group(3).strip()
                j, body = i + 1, []
                while j < len(lines) and lines[j].startswith(">"):
                    body.append(WIKI.sub(conv, lines[j]))
                    j += 1
                if mark in ("-", "+"):
                    out_lines += ["<details>",
                                  "<summary><b>%s</b></summary>" % (title or "展开查看"),
                                  ""] + body + ["", "</details>"]
                    total_details += 1
                else:
                    out_lines.append("> [!%s]" % ALERT.get(kind, "NOTE"))
                    if title:
                        out_lines += ["> **%s**" % title, ">"]
                    out_lines += body
                    total_alerts += 1
                i = j
                continue
            out_lines.append(WIKI.sub(conv, line))
            i += 1
        open(p, "w", encoding="utf-8").write("\n".join(out_lines))

    # 4) 修正「N 章」别名与实际章号不一致
    pat = re.compile(r"\[(第 )?(\d{1,2})( 章[^\]]*)\]\(([^)]+\.md)(#[^)]*)?\)")
    fixed = 0

    def fix(m):
        nonlocal fixed
        num, path = int(m.group(2)), m.group(4)
        mm = re.match(r"^(\d{2})-", os.path.basename(path))
        if not mm:
            return m.group(0)
        real = int(mm.group(1))
        if num == real:
            return m.group(0)
        fixed += 1
        return "[%s%d%s](%s%s)" % (m.group(1) or "", real, m.group(3), path, m.group(5) or "")

    for b, p in files.items():
        if os.path.basename(p).lower() in {k.lower() for k in KEEP}:
            continue
        t = open(p, encoding="utf-8").read()
        t2 = pat.sub(fix, t)
        if t2 != t:
            open(p, "w", encoding="utf-8").write(t2)

    # 5) 校验
    broken, leftover = [], 0
    for b, p in files.items():
        t = open(p, encoding="utf-8").read()
        leftover += len(WIKI.findall(t))
        for m in re.finditer(r"\]\(([^)]+)\)", t):
            u = m.group(1).strip()
            if u.startswith(("http", "mailto", "#")):
                continue
            path = u.split("#")[0]
            if path and not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(p), path))):
                broken.append((os.path.relpath(p, out), u))

    print("alert: %d | details: %d | 别名修正: %d" % (total_alerts, total_details, fixed))
    print("剩余双链: %d | 断链: %d" % (leftover, len(broken)))
    for x in broken[:10]:
        print("  断链", x)


if __name__ == "__main__":
    main()
