# Realm file format 9 (pre-Cluster) all-column-type fixture

`format9_alltypes.realm` is written by **realm-core v5.23.9's own public API**, not by
hand, so it is a genuine SDK-produced file rather than a reconstruction. v5.23.9 is the
last pre-Cluster line: its `group.hpp` documents file formats up to 9 and no further.

It is in the **normal (non-streaming) on-disk form** a real app produces, written through
`SharedGroup` + `WriteTransaction::commit()`. Note `Group::write()` produces the
*streaming* form instead (top ref 0 = 0xFFFFFFFFFFFFFFFF, real top ref in a 16-byte
footer ending with magic 0x3034125237E526C8); that form is not what an app leaves on disk.

## Contents

| table | rows | what it covers |
|---|---:|---|
| `class_Target` | 3 | link/linklist destination |
| `class_AllTypes` | 9 | one column per old ColumnType |
| `class_EnumStrings` | 12 | `Table::optimize(true)` -> `col_type_StringEnum` |

`class_AllTypes` columns, in order: `col_int`, `col_bool`, `col_string_short`,
`col_string_medium`, `col_string_big`, `col_binary`, `col_subtable`, `col_mixed`,
`col_olddatetime`, `col_timestamp`, `col_float`, `col_double`, `col_link`, `col_linklist`.
A BackLink column (type 14) exists implicitly from the link columns.

The three string columns are sized to land in the three different on-disk leaf forms.
realm-core `column_string.cpp` sets the boundaries at `small_string_max_size = 15`
(ArrayString) and `medium_string_max_size = 63` (ArrayStringLong), anything larger
being ArrayBigBlobs. So: 7 bytes -> Small, 40..48 -> Medium, 70000..70008 -> Big.

## Deliberately awkward values

- **Integers**: 0, 1, -1, 42, -42, 2147483647, -2147483648, 9007199254740993,
  -9007199254740993 (both signs, both 32-bit boundaries, and beyond 2^53).
- **Mixed**: one row per subtype tag, in row order 0..8 -- int 0, int 123456789,
  **int -987654321** (negative sign encoding), bool true, string, binary, float 2.5,
  double -4.75, timestamp 1700000000.500.
- **Subtable**: rows alternate empty / 1 entry / 2 entries, so both the empty and the
  populated case appear in one column.
- **LinkList**: lengths 1, 2, 3 cycling.
- **OldDateTime** (type 7) and **Timestamp** (type 8) are both present and distinct.

Expected values are in `expected.json`, generated from the C++ source's own constants.

## Reproducing

```
curl -L -o core.tar.gz https://codeload.github.com/realm/realm-core/tar.gz/refs/tags/v5.23.9
tar xzf core.tar.gz && cd realm-core-5.23.9
git init -q && git add -A && git -c user.email=a@b -c user.name=c commit -qm base && git tag v5.23.9
cmake -S . -B build -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DREALM_BUILD_LIB_ONLY=ON \
      -DREALM_NO_TESTS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 8      # QueryParser fails on a missing pegtl.hpp; librealm.a still builds
c++ -std=c++14 -O1 -o gen gen.cpp -Isrc -Ibuild/src build/src/realm/librealm.a \
    -lz -lpthread -framework CoreFoundation      # macOS; drop the framework on Linux
./gen format9_alltypes.realm
```

Built and run on macOS 15 arm64 with Apple clang 21 and CMake 4.4.3. The `git init`/`git tag`
is only so realm-core's `git_describe` resolves a version; `CMAKE_POLICY_VERSION_MINIMUM`
is needed because CMake 4 dropped `cmake_minimum_required(VERSION 3.4)`.

`gen.cpp` is the generator. Extend it and re-run to cover more cases.
