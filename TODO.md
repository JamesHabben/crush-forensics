# TODO — Realm Parser/Viewer

Source: "Mobile Forensics – The File Format Handbook", Chapter 8 (Cobley/Geneste 2022),
cross-checked against the example file `de.formel1/files/f1de.realm` (786 432 bytes).

---

## 1. File Header (24 bytes) — fully parsed, confirmed correct

Structure defined in `alloc_slab.hpp` (Realm Core source):

```
Offset  Size  Field            Notes
0x00     8    m_top_ref[0]     little-endian uint64 — file offset of root array A
0x08     8    m_top_ref[1]     little-endian uint64 — file offset of root array B
0x10     4    m_mnemonic       ASCII "T-DB" (0x54 2D 44 42); magic value
0x14     2    m_file_format    file format version; seen 0x18 (=24) in practice
0x16     1    m_reserved       always 0x00 at time of writing
0x17     1    m_flags          bit 0 (LSB): 0 = top_ref[0] active, 1 = top_ref[1] active
                               bits 1–7: unused at time of writing
```

**Journaling / WAL analogy**: The two top_refs are the Realm equivalent of SQLite's WAL.
The "current" (read-consistent) branch is the one selected by flags bit 0. All writes go
to the *other* branch. Checkpoint = swap the flag.

f1de.realm values:
- top_ref[0] = 0x10228 (66 088), top_ref[1] = 0x107a0 (67 488), flags = 0x01 → top_ref[1] active.

---

## 2. Realm Arrays — the only structure after the header

After the 24-byte file header the file consists **exclusively** of Realm Arrays arranged in
a B+ tree. Two kinds:

| Type             | has_refs | Role                                  |
|------------------|----------|---------------------------------------|
| Reference Array  | 1        | Branch node — payload = file offsets  |
| Data Array       | 0        | Leaf node — payload = actual values   |

Arrays start with a fixed **8-byte header**, followed by a variable-length payload.
Consecutive arrays can be located by scanning for the 4-byte checksum pattern `AAAA`
(0x41414141).

---

## 3. Array Header (8 bytes) — TO BE IMPLEMENTED

```
Offset  Size  Field            Notes
0x00     4    checksum         Always 0x41414141 ("AAAA") — dummy, may change in future
0x04     1    flags            See bit-group table below
0x05     3    size             Big-endian uint24 — number of *elements* in payload
```

### 3a. Flags byte — bit groups (MSB = bit 7)

```
Bit(s)  Mask  Name                 Values / Meaning
7       0x80  is_inner_bptree_node 1 = inner B+ tree node; always sets has_refs too
6       0x40  has_refs             1 = Reference Array (payload = file offsets to children)
                                   0 = Data Array (payload = actual data values)
5       0x20  context_flag         purpose unclear, rarely set; can identify leaf node type
[4:3]   0x18  width_scheme         2-bit value 0–2; selects payload size formula (see below)
[2:0]   0x07  width_ndx            3-bit index 0–7 into width translation table (see below)
```

Python extraction:
```python
is_inner     = (flags >> 7) & 0x1
has_refs     = (flags >> 6) & 0x1
context_flag = (flags >> 5) & 0x1
width_scheme = (flags >> 3) & 0x3   # bits [4:3]
width_ndx    = flags & 0x7           # bits [2:0]
```

### 3b. width_ndx → width translation table

```
width_ndx :  0   1   2   3   4    5    6    7
width      :  0   1   2   4   8   16   32   64
```

"width" = size of one element (in bits for scheme 0, in bytes for scheme 1).

### 3c. width_scheme → payload byte count formula

```
width_scheme  Meaning            Formula
0             size in bits       payload_bytes = ceil(width × size / 8)
1             size in bytes      payload_bytes = width × size
2             ignore width       payload_bytes = size
```

After computing `payload_bytes`, **round up to the next 8-byte boundary**:
```python
payload_bytes = (payload_bytes + 7) & ~7
```

Total array byte length = 8 (header) + payload_bytes_aligned.

### 3d. Worked example from PDF (demo.realm first array)

Header bytes: `41 41 41 41  0E  00 00 05`
- checksum = "AAAA"
- flags = 0x0E = 0b00001110
  - is_inner = 0, has_refs = 0, context_flag = 0
  - width_scheme = 01 = 1 → formula: width × size
  - width_ndx = 110 = 6 → width = 32
- size = 5

payload_bytes = 32 × 5 = 160, already aligned → **total array = 168 bytes** ✓ (confirmed in HxD)

### 3e. f1de.realm active top node (offset 0x107a0)

Header bytes: `41 41 41 41  46  00 00 0B`
- flags = 0x46 = 0b01000110
  - is_inner = 0, has_refs = 1 → **Reference Array**
  - context_flag = 0
  - width_scheme = 00 = 0 → formula: ceil(width × size / 8)
  - width_ndx = 110 = 6 → width = 32 (bits)
- size = 11

payload_bytes = ceil(32 × 11 / 8) = 44, aligned to 48 → **total array = 56 bytes**
→ 11 × 4-byte file offsets pointing to the 11 top-level Group entries.

---

## 4. B+ Tree Traversal — open question / to be implemented

Starting point: active top_ref offset from the file header.
1. Read the 8-byte array header at that offset.
2. If has_refs=1: each payload element is a file offset — recurse into each child.
3. If has_refs=0: this is a data array — interpret payload according to width/scheme.
4. Repeat until all leaves are reached.

**Schema location**: class/table names are visible as null-terminated ASCII strings
beginning immediately after the file header (offset 0x18 in f1de.realm) — part of the
"metadata" group, which is the first entry of the root Reference Array (top_ref → offset 24).

Classes found in f1de.realm (visible in raw hex):
`metadata`, `class_AdminInfo`, `class_AdminMenu`, `class_Article`, `class_ArticleEDP`,
`class_ArticleType`, `class_ArticleTypeEDP`, `class_Author`, `class_AuthorEDP`,
`class_Country`, `class_Driver`, `class_DriverEDP`, `class_Event`, `class_EventEDP`,
`class_EventStandings`, `class_ItemsLoadedForArticle`, `class_ItemsLoadedForEvent`,
`class_ItemsLoadedForPhoto`, `class_ItemsLoadedForVideo`, `class_Livetext`,
`class_Location`, `class_LocationEDP`, `class_Photo`, `class_PhotoEDP`,
`class_PhotoNextPrev`, `class_PhotoSize`, `class_Promotion`,
`class_RaceHubDetailChampionship`, `class_RaceHubSessionType`, …

---

## 5. Implementation Backlog

### 5.1 Array header decoder (prerequisite for everything else)
- Parse checksum, flags (all 5 bit groups), size from 8-byte header
- Compute payload_bytes and total array size
- Return structured dict: `{checksum, is_inner, has_refs, context_flag, width_scheme, width_ndx, width, size, payload_bytes}`

### 5.2 Schema / Tables tab in viewer
- Follow top_ref → root Reference Array → entry[0] (metadata group)
- Walk metadata group to extract all `class_*` strings
- Display as a "Schema" or "Tables" tab

### 5.3 Both top_refs decoded side-by-side + diff
- Decode both top_ref[0] and top_ref[1] array headers
- Show header fields, size, child-count, payload offset for each
- Show diff summary (which fields differ) — useful for WAL-state analysis

### 5.4 Full B+ tree traversal + row extraction (complex, out of scope for now)
- Requires recursive descent, column type mapping, and schema-guided decoding



## Status (2026-04-10)

All items in §5.1–5.3 implemented and tested:
- Array header decoder ✓
- Schema / Tables tab in viewer ✓ (TreeViewer + TableViewer)
- Both top_refs decoded side-by-side + diff ✓
- String columns ✓  |  Scalar (int/bool) columns ✓  |  Blob columns ✓

Remaining: §5.4 (full B+ tree traversal + row extraction, column names from schema)