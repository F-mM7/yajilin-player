#!/usr/bin/env python3
"""puzzles_data.js を sources.json に列挙した puzz.link の URL から再生成する。

sources.json は問題ごとに id / title / source_url を持つ。source_url は
  https://puzz.link/p?yajilin/<列数>/<行数>/<盤面>
の形で、<盤面> は pzprjs の Encode.decodeArrowNumber16 と同じ方式で符号化されている。
  - '0'-'4' + 16進1桁 : 向き=先頭の数字, 数字=16進1桁('.' なら ?)
  - '5'-'9' + 16進2桁 : 向き=先頭の数字-5, 数字=16進2桁
  - '-' + 向き1桁 + 16進3桁 : 数字が 0x100 以上の場合
  - '+' : 数字なしの白ヒント(qnum=-3)。ヤジリンでは意味を持たないためエラーにする
  - 'a'-'z' : 空マスを (値-9) 個飛ばす
  向きは 0=なし / 1=上 / 2=下 / 3=左 / 4=右。
ここでは盤面をヒントの [行, 列, 向き, 数字] リストへ展開して puzzles_data.js に書き出す。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SOURCES_PATH = ROOT / "sources.json"
OUTPUT_PATH = ROOT / "puzzles_data.js"

# 盤面の後ろに "/" が付いた URL もある(pzprjs は "/" 区切りで読むので無視される)
URL_PATTERN = re.compile(r"^https://puzz\.link/p\?yajilin/(\d+)/(\d+)/([0-9a-z.+\-]*)/?$")
DIRS = {0: "N", 1: "U", 2: "D", 3: "L", 4: "R"}
QNUM_UNKNOWN = -2  # pzprjs の「?」


def decode_arrow_numbers(body, rows, cols, label):
    """pzprjs の decodeArrowNumber16 相当。マス番号 -> (向き, 数字) の辞書を返す。"""
    n = rows * cols
    cells = {}
    c = 0
    i = 0
    while i < len(body):
        if c >= n:
            raise ValueError(f"盤面がマス数を超えて続いています: 位置 {i} 以降 {body[i:]!r}")
        ca = body[i]
        if ca == "+":
            raise ValueError(f"未対応のヒント '+'(qnum -3) がマス {c} にあります")
        elif "0" <= ca <= "4":
            ca1 = body[i + 1:i + 2]
            if not ca1:
                raise ValueError(f"盤面が途中で切れています: 位置 {i}")
            cells[c] = (int(ca), QNUM_UNKNOWN if ca1 == "." else int(ca1, 16))
            i += 2
        elif "5" <= ca <= "9":
            digits = body[i + 1:i + 3]
            if len(digits) != 2:
                raise ValueError(f"盤面が途中で切れています: 位置 {i}")
            cells[c] = (int(ca) - 5, int(digits, 16))
            i += 3
        elif ca == "-":
            digits = body[i + 1:i + 5]
            if len(digits) != 4:
                raise ValueError(f"盤面が途中で切れています: 位置 {i}")
            cells[c] = (int(digits[0], 16), int(digits[1:], 16))
            i += 5
        elif "a" <= ca <= "z":
            c += int(ca, 36) - 10
            i += 1
        else:
            raise ValueError(f"不明な文字 {ca!r}: 位置 {i}")
        c += 1
    if c > n:
        raise ValueError(f"空マス飛ばしがマス数を超えています: {c} > {n}")
    if c < n:
        # pzprjs は残りを空マスとして読むので表示上は同じになるが、URL 自体が欠けている可能性があるため追跡できるようにする
        print(f"警告: {label}: 盤面が {c}/{n} マスで終わっています。残りは空マスとして扱います", file=sys.stderr)
    return cells


def decode_entry(entry):
    m = URL_PATTERN.match(entry["source_url"])
    if not m:
        sys.exit(f"ヤジリンの puzz.link URL ではありません: {entry['id']} {entry['source_url']}")
    cols, rows, body = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        cells = decode_arrow_numbers(body, rows, cols, entry["id"])
    except ValueError as e:
        sys.exit(f"{entry['id']}: {e}")
    clues = []
    for c in sorted(cells):
        qdir, qnum = cells[c]
        if qdir not in DIRS:
            sys.exit(f"{entry['id']}: 不明な向き {qdir} (マス {c})")
        if qnum < 0 and qnum != QNUM_UNKNOWN:
            sys.exit(f"{entry['id']}: 不明な数字 {qnum} (マス {c})")
        clues.append([c // cols, c % cols, DIRS[qdir], None if qnum == QNUM_UNKNOWN else qnum])
    return {
        "id": entry["id"],
        "rows": rows,
        "cols": cols,
        "clues": clues,
        "source_url": entry["source_url"],
    }


def load_puzzles():
    with SOURCES_PATH.open(encoding="utf-8") as f:
        sources = json.load(f)
    ids = [s["id"] for s in sources]
    if len(set(ids)) != len(ids):
        sys.exit(f"id が重複しています: {SOURCES_PATH}")
    return [decode_entry(s) for s in sources]


def compact_json(puzzles):
    # ヒントを1要素1行にすると大盤面で数万行になるため、問題1件を1ブロック、ヒントリストは1行で書く
    blocks = []
    for p in puzzles:
        lines = [
            "  {",
            f'    "id": {json.dumps(p["id"])},',
            f'    "rows": {p["rows"]},',
            f'    "cols": {p["cols"]},',
            f'    "clues": {json.dumps(p["clues"], separators=(",", ":"))},',
            f'    "source_url": {json.dumps(p["source_url"])}',
            "  }",
        ]
        blocks.append("\n".join(lines))
    return "[\n" + ",\n".join(blocks) + "\n]"


def main():
    puzzles = load_puzzles()
    if not puzzles:
        sys.exit(f"パズルが見つかりません: {SOURCES_PATH}")
    header = (
        "// ヤジリン問題データ。extract_puzzles.py が sources.json の puzz.link URL から生成する(手で編集しない)。\n"
        "// clues は [行, 列, 向き(U/D/L/R/N), 数字](0始まり、N は矢印なし、数字 null は「?」)。\n"
    )
    OUTPUT_PATH.write_text(header + f"const PUZZLES = {compact_json(puzzles)};\n", encoding="utf-8")
    print(f"{len(puzzles)} puzzles written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
