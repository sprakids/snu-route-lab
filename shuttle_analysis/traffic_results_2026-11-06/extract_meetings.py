"""Extract unencrypted public HWP/DOCX text for source discovery, retaining originals."""
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "runtime/pydeps"))
import olefile


def hwp_text(path):
    parts = []
    with olefile.OleFileIO(path) as ole:
        header = ole.openstream("FileHeader").read()
        assert header.startswith(b"HWP Document File")
        flags = struct.unpack_from("<I", header, 36)[0]
        if flags & 6:
            raise ValueError("Encrypted/distribution document; do not attempt extraction")
        sections = [s for s in ole.listdir() if s[0] == "BodyText" and s[-1].startswith("Section")]
        for section in sorted(sections, key=lambda s: int(s[-1][7:])):
            data = ole.openstream(section).read()
            if flags & 1:
                data = zlib.decompress(data, -15)
            pos = 0
            while pos + 4 <= len(data):
                tag_header = struct.unpack_from("<I", data, pos)[0]
                pos += 4
                tag, size = tag_header & 1023, tag_header >> 20
                if size == 4095:
                    size = struct.unpack_from("<I", data, pos)[0]
                    pos += 4
                assert pos + size <= len(data)
                if tag == 67:
                    text = data[pos:pos + size].decode("utf-16-le", errors="replace")
                    # These are discovery strings, not a layout-preserving rendering.
                    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
                    if text.strip():
                        parts.append(text)
                pos += size
    return "\n".join(parts)


def docx_text(path):
    with zipfile.ZipFile(path) as archive:
        doc = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    return "\n".join("".join(p.itertext()) for p in doc.findall(".//w:p", ns))


if __name__ == "__main__":
    results = []
    for p in (ROOT / "sources").glob("M*_A*.*"):
        if p.suffix not in (".hwp", ".docx") or "별첨" in p.name:
            continue
        text = hwp_text(p) if p.suffix == ".hwp" else docx_text(p)
        out = p.with_suffix(p.suffix + ".txt")
        out.write_text(text, encoding="utf-8")
        matches = []
        for m in re.finditer(r"교통.{0,4}총조사|교통.{0,4}조사|서울대입구|낙성대|대학동", text):
            matches.append({"offset": m.start(), "text": text[max(0, m.start()-180):m.start()+1500]})
        results.append({"file": str(p.relative_to(ROOT)), "chars": len(text), "matches": matches})
        print(p.name, "CHARS", len(text), "MATCHES", len(matches))
        for hit in matches[:5]:
            print(hit["text"])
    (ROOT / "meeting_text_hits.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
