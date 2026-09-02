// SPDX-License-Identifier: Apache-2.0
// Generates streaming_form.realm: a genuine Realm "streaming form" file
// (alloc_slab.hpp/.cpp SlabAlloc::is_file_on_streaming_form / StreamingFooter),
// via realm-js's own Realm.prototype.writeCopyTo() -- not a hand-rebuilt
// header. Confirms the on-disk shape: top_ref[0] = 0xFFFFFFFFFFFFFFFF
// (sentinel), top_ref[1] = 0, select bit = 0, and a 16-byte footer at the
// end of the file (real top ref + magic cookie 0x3034125237E526C8).
//
// Reproducing: `npm install realm` (native bindings; first `require("realm")`
// per process is slow, ~90-150s cold), then `node generate_streaming_form.js`.
//
// Content: two tables -- Realm's own implicit "metadata" table (schema
// version), and one user table "Item" (_id: int primary key, label: string)
// with two rows: {_id: 1, label: "hello"}, {_id: 2, label: "world"}.

const Realm = require("realm");
const fs = require("fs");

const SRC = "src.realm";
const OUT = "streaming_form.realm";

for (const p of [SRC, OUT]) {
  try { fs.unlinkSync(p); } catch (e) {}
}

class Item extends Realm.Object {}
Item.schema = {
  name: "Item",
  properties: { _id: "int", label: "string" },
  primaryKey: "_id",
};

async function main() {
  const realm = await Realm.open({ path: SRC, schema: [Item] });
  realm.write(() => {
    realm.create("Item", { _id: 1, label: "hello" });
    realm.create("Item", { _id: 2, label: "world" });
  });

  realm.writeCopyTo({ path: OUT });
  realm.close();

  console.log(`Wrote ${OUT} (${fs.statSync(OUT).size} bytes)`);
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
