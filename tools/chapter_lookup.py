"""ดึงแถวจากเอกสารกลางที่เกี่ยวกับต้นฉบับบท NNN ในครั้งเดียว (D046)

ใช้: python -X utf8 tools/chapter_lookup.py NNN [--only glossary,characters,world,sources,relations]

แหล่งที่ดึง (แสดงเลขบรรทัดเพื่อแก้แถวเดิมได้ตรงจุด):
- GLOSSARY.md, WORLD.md: แถวตารางที่คำจีนในช่องแรกปรากฏในต้นฉบับบทนี้
- CHARACTERS.md: แถวทะเบียนที่คำจีนในช่องที่สองปรากฏในต้นฉบับบทนี้
- docs/SOURCE_ISSUES.md: แถวที่ช่องตำแหน่งอ้างบทนี้ (เช่น 052:3 หรือ 052 ย4)
- CHARACTERS.md หัวข้อ “บันทึกความสัมพันธ์และสรรพนาม”: บรรทัดที่ทุกฝ่ายเป็นตัวละครที่ปรากฏในบทนี้
ค่าเริ่มต้นเป็นโหมดดัชนี: ตัดแต่ละช่องที่ยาวเกิน --width ตัวอักษร (ลงท้าย …) และไม่แสดงช่องอ้างอิงตำแหน่ง
ของ GLOSSARY/CHARACTERS; WORLD.md แสดงเฉพาะ จีน | ไทย | ประเภท | เจ้าของ | บทอ้างอิง (ไม่แสดงคุณสมบัติ
และข้อจำกัด เพราะแถวเติมย้อนหลังบท 002–035 ยาวหลายพันตัวอักษร)
ถ้าฉากใช้คุณสมบัติ ข้อจำกัด หรือหมายเหตุที่ถูกตัดของรายการใด ให้อ่านแถวเต็มที่เลขบรรทัดนั้น
หรือรันซ้ำด้วย --only ส่วนนั้น --full --width 0
ใช้แทนการ grep ทีละคำ คำจีนตัวเดียวไม่นำมาจับ (ขึ้นแทบทุกบท) ถ้าต้องการคำตัวเดียวให้ grep เอง
คำเรียกและคำแทนตัวที่ยืนยันบท 001–035 ยังดึงด้วย tools/address_lookup.py
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CJK = re.compile(r"[㐀-鿿豈-﫿\U00020000-\U0002ffff]{2,}")
HEADER_FIRST = {"จีน", "ชื่อจีน", "รหัส"}


def chapter_text(num: str) -> str:
    files = sorted((ROOT / "chapters").glob(f"{num}-*.md"))
    if not files:
        sys.exit(f"ไม่พบต้นฉบับบท {num}")
    return files[0].read_text(encoding="utf-8")


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table_rows(path: Path):
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("|") or line.startswith("|---"):
            continue
        row = cells(line)
        if row and row[0] not in HEADER_FIRST:
            yield no, line, row


def match_terms(cell: str, text: str) -> bool:
    cell = re.sub(r"[（(][^）)]*[）)]", "", cell)
    return any(t in text for t in CJK.findall(cell))


def shorten(line: str, width: int) -> str:
    if width <= 0:
        return line
    parts = cells(line)
    parts = [p if len(p) <= width else p[:width] + "…" for p in parts]
    return "| " + " | ".join(parts) + " |"


# ช่องที่แสดงในโหมดดัชนี (นับจาก 0) ตามจำนวนช่องของแถว; ช่องอ้างอิงตำแหน่งตัดสั้นกว่าปกติ
INDEX_COLS = {
    "glossary": {6: [0, 1, 2, 3, 5]},
    "characters": {6: [0, 1, 2, 3, 4]},
    "world": {8: [0, 1, 2, 3, 6]},
}
REF_COL = {"world": 6}


def index_view(key: str, line: str, width: int) -> str:
    parts = cells(line)
    keep = INDEX_COLS.get(key, {}).get(len(parts))
    if keep is None:
        return shorten(line, width)
    out = []
    for i in keep:
        w = min(width, 60) if REF_COL.get(key) == i and width > 0 else width
        p = parts[i]
        out.append(p if w <= 0 or len(p) <= w else p[:w] + "…")
    return "| " + " | ".join(out) + " |"


def by_term(path: Path, col: int, text: str):
    return [(no, line) for no, line, row in table_rows(path)
            if len(row) > col and match_terms(row[col], text)]


def sources(num: str):
    pat = re.compile(rf"(?<!\d){num}(?=[:\s ย]|$)")
    return [(no, line) for no, line, row in table_rows(ROOT / "docs" / "SOURCE_ISSUES.md")
            if len(row) > 1 and pat.search(row[1])]


def relations(text: str):
    path = ROOT / "CHARACTERS.md"
    names = set()
    for _, _, row in table_rows(path):
        if len(row) > 2 and match_terms(row[1], text):
            names.update(n.strip() for n in row[2].split("/") if n.strip())
    out, inside = [], False
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            inside = "ความสัมพันธ์" in line
            continue
        if not inside or not line.startswith("- ") or ":" not in line:
            continue
        sides = re.split(r"→|↔|<->|->", line[2:].split(":", 1)[0])
        if len(sides) > 1 and all(any(n in s for n in names) for s in sides):
            out.append((no, line))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("num")
    ap.add_argument("--only", default="glossary,characters,world,sources,relations")
    ap.add_argument("--width", type=int, default=100, help="ความยาวสูงสุดต่อช่อง 0 = ไม่ตัด")
    ap.add_argument("--full", action="store_true", help="แสดงทุกช่อง ไม่ใช้โหมดดัชนี")
    args = ap.parse_args()
    num = args.num.zfill(3)
    text = chapter_text(num)
    want = set(args.only.split(","))
    groups = [
        ("glossary", "GLOSSARY.md", lambda: by_term(ROOT / "GLOSSARY.md", 0, text)),
        ("characters", "CHARACTERS.md", lambda: by_term(ROOT / "CHARACTERS.md", 1, text)),
        ("world", "WORLD.md", lambda: by_term(ROOT / "WORLD.md", 0, text)),
        ("sources", "docs/SOURCE_ISSUES.md", lambda: sources(num)),
        ("relations", "CHARACTERS.md ความสัมพันธ์", lambda: relations(text)),
    ]
    for key, label, fn in groups:
        if key not in want:
            continue
        rows = fn()
        print(f"\n=== {label}: {len(rows)} แถว ===")
        for no, line in rows:
            if key == "relations":
                out = line
            elif not args.full and key in INDEX_COLS:
                out = index_view(key, line, args.width)
            else:
                out = shorten(line, args.width)
            print(f"{no}: {out}")


if __name__ == "__main__":
    main()
