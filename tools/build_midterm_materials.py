"""Generate defense outline, speaking notes and Word drafts; no device access.

Dependency: python-docx. Run --verify once to refresh offline evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from docx import Document
from docx.shared import Pt as DocPt, Inches as DocInches, RGBColor as DocColor
from docx.oxml import OxmlElement as DocElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/midterm"
FONT = "Microsoft YaHei"


def command(args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")


def collect_evidence():
    py = ROOT / ".venv/Scripts/python.exe"
    unit = command([str(py), "-m", "pytest", "-q"])
    replay = command([str(py), "-m", "benchmarks.runner"])
    if unit.returncode or replay.returncode:
        raise RuntimeError(f"Offline validation failed: {unit.stdout}\n{unit.stderr}\n{replay.stderr}")
    benchmark = json.loads(replay.stdout)
    if benchmark.get("all_passed") is not True:
        raise RuntimeError("Benchmark did not pass")
    unit_summary = next((line.strip() for line in reversed(unit.stdout.splitlines()) if "passed" in line), "")
    unit_count = re.search(r"(\d+) passed", unit_summary)
    history = []
    for filename in ("console_experiment_complete.json", "console_route_missing_complete.json"):
        path = ROOT / "reports/live" / filename
        if not path.exists():
            history.append({"path": str(path.relative_to(ROOT)), "status": "MISSING"})
            continue
        raw = path.read_bytes()
        report = json.loads(raw)
        trials = report.get("trials", [])
        history.append({
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "status": "historical local report; not a new run",
            "file_mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            "requested_trials": report.get("requested_trials"),
            "passed_trials": report.get("passed_trials"),
            "all_passed": report.get("all_passed"),
            "trials": [{"passed": t.get("passed"), "fault_type": (t.get("diagnosis") or {}).get("fault_type"),
                        "fault_device": (t.get("diagnosis") or {}).get("fault_device"),
                        "recovery_success": (t.get("recovery") or {}).get("success"),
                        "post_recovery_facts": (t.get("post_recovery") or {}).get("facts")} for t in trials],
        })
    data = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_head": command(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "source_note": "HEAD before committing this material bundle; documentation changes do not constitute a live rerun",
        "pytest": {"command": "python -m pytest -q", "exit_code": unit.returncode,
                   "passed": int(unit_count.group(1)) if unit_count else None, "summary": unit_summary},
        "benchmark": {k: benchmark.get(k) for k in ("total", "passed", "failed", "all_passed", "execution_modes")},
        "historical_live_reports": history,
        "current_release_live_acceptance": "PENDING; no device connection in this material preparation",
    }
    (OUT / "evidence.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def markdown_to_docx(source):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = DocInches(8.5), DocInches(11)
    sec.top_margin = sec.bottom_margin = DocInches(.7)
    sec.left_margin = sec.right_margin = DocInches(.85)
    # Some bundled Word templates inherit a colored rule beneath the title.
    for node in list(doc.styles.element.iter(qn("w:pBdr"))):
        node.getparent().remove(node)
    for name in ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3"):
        style = doc.styles[name]
        style.font.name = FONT
        style.font.color.rgb = DocColor(0, 0, 0)
        style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
    doc.styles["Normal"].font.size = DocPt(11)
    doc.styles["Normal"].paragraph_format.space_after = DocPt(6)
    doc.styles["Normal"].paragraph_format.line_spacing = 1.2
    lines=source.read_text(encoding="utf-8").splitlines()
    code=False
    i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith("```"):
            code=not code
            i+=1
            continue
        if not line.strip():
            i+=1
            continue
        if line.startswith("|") and not code:
            rows=[]
            while i<len(lines) and lines[i].startswith("|"):
                if not re.fullmatch(r"[| :\-]+",lines[i]):
                    rows.append([c.strip().replace('`','') for c in lines[i].strip('|').split('|')])
                i+=1
            table=doc.add_table(rows=1, cols=len(rows[0]))
            table.style="Table Grid"
            table.autofit = False
            widths = ([1.7, 1.45, 3.65] if len(rows[0]) == 3 else [6.8/len(rows[0])]*len(rows[0]))
            for col, width in zip(table.columns, widths): col.width = DocInches(width)
            header = DocElement("w:tblHeader")
            table.rows[0]._tr.get_or_add_trPr().append(header)
            for idx,row in enumerate(rows):
                cells=table.rows[0].cells if idx==0 else table.add_row().cells
                for ci,(cell,value) in enumerate(zip(cells,row)):
                    cell.width=DocInches(widths[ci])
                    cell.text=value
                    props=cell._tc.get_or_add_tcPr()
                    valign=DocElement("w:vAlign"); valign.set(qn("w:val"),"center"); props.append(valign)
                    borders=DocElement("w:tcBorders")
                    for edge in ("top","left","bottom","right"):
                        e=DocElement("w:"+edge); e.set(qn("w:val"),"single"); e.set(qn("w:sz"),"4"); e.set(qn("w:color"),"D9D9D9"); borders.append(e)
                    props.append(borders)
                    shd=DocElement("w:shd"); shd.set(qn("w:fill"),"E6EDF2" if idx == 0 else "FFFFFF"); props.append(shd)
                    for para in cell.paragraphs:
                        para.paragraph_format.space_before=DocPt(4)
                        para.paragraph_format.space_after=DocPt(4)
                        para.paragraph_format.line_spacing=1.15
                        for run in para.runs: run.font.size=DocPt(10.5); run.bold=(idx==0)
            continue
        if line.startswith("#") and not code:
            depth=len(line)-len(line.lstrip('#'))
            doc.add_heading(line[depth:].strip(), level=min(depth-1,3))
        else:
            p=doc.add_paragraph(line.replace('`',''))
            if not code:
                p.paragraph_format.keep_together = True
            if code:
                p.paragraph_format.space_after=DocPt(1)
                for r in p.runs: r.font.size=DocPt(9)
        i+=1
    footer=sec.footer.paragraphs[0]
    footer.text="NetPath-Doctor · 中期准备材料 · " + datetime.now().date().isoformat()
    for r in footer.runs: r.font.size=DocPt(9)
    doc.save(source.with_suffix('.docx'))


def make_script(rows):
    body = "# 5 分钟展示讲稿与操作卡\n\n按老师转录安排：5 分钟展示（含功能演示），约 5 分钟提问。若学院新通知不同，以新通知为准。主汇报 8 页；A1—A4 为备用答疑，不逐页读。\n\n"
    body += "时间分配：20＋25＋35＋30＋30＋30＋90＋40 秒＝300 秒。除演示外约 210 秒；先按此稿熟悉，再以实际彩排计时调整。备注中的来源与补充说明不用照读。\n\n"
    for row in rows[:8]:
        body += f"## 第 {row['id']} 页 · {row['title'].replace(chr(10),'')}\n\n{row['notes']}\n\n"
    body += "## 开始前操作卡\n\n确认拓扑已启动、无其他实验正在运行；预先打开本轮 JSON 和原文目录，准备演示命令，不现场敲长命令。故障实验结束后必须确认恢复；需要手工处置时先停止演示并保留错误记录。单次全流程超过 90 秒，改展示只读诊断与已保存的完整报告，录像作为明确标注的备份。\n\n"
    body += "## 提问时的查找顺序\n\n代码问题看 A1 和《代码导读与答疑》；能力边界看 A2；Agent、Benchmark 和恢复机制看 A3；来源和版本看 A4 与 evidence.json。未知问题如实说尚未验证，并给出计划验证的方法。\n"
    (OUT/"讲稿与演示.md").write_text(body,encoding="utf-8")
    outline = "# PPT 大纲与制作交接\n\n主汇报 8 页＋答疑附录 4 页。本阶段仅完成大纲，不制作最终 PPT。总展示 5 分钟，含约 90 秒演示；提问约 5 分钟。来源为 slides.json 和 evidence.json。\n\n"
    for row in rows:
        outline += f"## {row['id']} {row['title'].replace(chr(10), '')}\n\n{row['subtitle']}\n\n"
        outline += "页面要点：\n\n" + "\n".join("- " + b for b in row["bullets"])
        outline += f"\n\n配图建议：{row['visual']}。\n\n素材和边界：{row['assets']}\n\n讲解备注：{row['notes']}\n\n"
    (OUT/"PPT大纲.md").write_text(outline.rstrip() + "\n",encoding="utf-8")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    if args.verify: collect_evidence()
    evidence=json.loads((OUT/"evidence.json").read_text(encoding="utf-8"))
    rows=json.loads((OUT/"slides.json").read_text(encoding="utf-8"))
    count=str(evidence["pytest"]["passed"])
    for row in rows:
        row["notes"]=row["notes"].replace("{test_count}",count)
    rows[5]["subtitle"]="离线检查时间："+evidence["checked_at_utc"]+"；本轮未连接 eNSP"
    make_script(rows)
    for name in ("讲稿与演示.md","中期检查报告_技术稿.md"):
        markdown_to_docx(OUT/name)
    print(json.dumps({"outline":str(OUT/"PPT大纲.md"),"planned_slides":len(rows),"pytest":evidence["pytest"]["summary"],"benchmark":evidence["benchmark"]},ensure_ascii=False))


if __name__=="__main__":
    main()
