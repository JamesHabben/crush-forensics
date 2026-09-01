// Generator for crush/tests/fixtures/all_types_v24.realm.
//
// Produces a real file-format-24 Realm database via the actual realm-js
// SDK (not hand-built bytes), covering every modern column type -- see
// issue #55 follow-up (project memory). To regenerate:
//
//   npm install realm
//   node generate_all_types_v24.js
//   cp all_types_v24.realm ../fixtures/all_types_v24.realm
//   # then update checksums.json with the new file's sha256
//
// Two real bugs in crush/parsers/realm_parser.py were found and fixed by
// testing against this file's output cross-checked against realm-js's own
// values: LinkList wrongly applying the single-Link "+1/0=null" encoding
// to list elements (which are plain 0-based, unadjusted), and _decode_bid
// (Decimal128) having the combination-field bit layout wrong entirely
// (fixed by brute-force solving against row 0/1's known-correct values),
// plus a precision-loss bug from Python's ambient decimal context
// silently rounding 34-digit Bid128 coefficients to 28 digits.
const Realm = require("realm");
const { BSON } = Realm;
const path = require("path");
const fs = require("fs");

const OUT_PATH = path.join(__dirname, "all_types_v24.realm");
if (fs.existsSync(OUT_PATH)) fs.unlinkSync(OUT_PATH);

// TargetRecord: the object every Link/LinkList/TypedLink/BackLink points at.
const TargetSchema = {
  name: "TargetRecord",
  properties: {
    _id: "int",
    label: "string",
    // BackLink: reverse of AllTypesRecord.linkList
    incoming: {
      type: "linkingObjects",
      objectType: "AllTypesRecord",
      property: "linkList",
    },
  },
  primaryKey: "_id",
};

const AllTypesSchema = {
  name: "AllTypesRecord",
  properties: {
    _id: "int",
    intCol: "int",
    boolCol: "bool",
    stringCol: "string",
    dataCol: "data",
    floatCol: "float",
    doubleCol: "double",
    decimalCol: "decimal128",
    dateCol: "date",
    uuidCol: "uuid",
    objectIdCol: "objectId",
    linkCol: "TargetRecord",
    linkList: "TargetRecord[]",
    mixedCol: "mixed",
    // Nested-collection Mixed cells (format 24 feature): a Mixed holding a
    // List and a Mixed holding a Dictionary, both containing Mixed values.
    mixedWithNestedList: "mixed",
    mixedWithNestedDict: "mixed",
    dictCol: "mixed{}",
    setCol: "int<>",
    listOfInt: "int[]",
  },
  primaryKey: "_id",
};

const config = {
  path: OUT_PATH,
  schema: [TargetSchema, AllTypesSchema],
  schemaVersion: 1,
};

(async () => {
  const realm = await Realm.open(config);

  realm.write(() => {
    const target = realm.create("TargetRecord", { _id: 1, label: "target-one" });
    realm.create("TargetRecord", { _id: 2, label: "target-two" });

    realm.create("AllTypesRecord", {
      _id: 1,
      intCol: 42,
      boolCol: true,
      stringCol: "hello world",
      dataCol: new Uint8Array([1, 2, 3, 4, 5]).buffer,
      floatCol: 3.140000104904175,
      doubleCol: 2.718281828,
      decimalCol: BSON.Decimal128.fromString("12345.6789"),
      dateCol: new Date("2024-01-15T10:30:00Z"),
      uuidCol: new BSON.UUID("550e8400-e29b-41d4-a716-446655440000"),
      objectIdCol: new BSON.ObjectId("507f1f77bcf86cd799439011"),
      linkCol: target,
      linkList: [target, realm.objectForPrimaryKey("TargetRecord", 2)],
      mixedCol: "a plain mixed string",
      mixedWithNestedList: [1, "two", 3.0, true],
      mixedWithNestedDict: { a: 1, b: "two", c: [1, 2, 3] },
      dictCol: { keyOne: "val1", keyTwo: 2, keyThree: true },
      setCol: [10, 20, 30],
      listOfInt: [100, 200, 300],
    });

    // Second row with negative/edge values, exercising the Mixed
    // negative-number path and a null-able mixed cell.
    realm.create("AllTypesRecord", {
      _id: 2,
      intCol: -42,
      boolCol: false,
      stringCol: "",
      dataCol: new Uint8Array([]).buffer,
      floatCol: -1.5,
      doubleCol: -2.5,
      decimalCol: BSON.Decimal128.fromString("-99.99"),
      dateCol: new Date("1969-12-31T23:59:59Z"),
      uuidCol: new BSON.UUID(),
      objectIdCol: new BSON.ObjectId(),
      linkCol: null,
      linkList: [],
      mixedCol: -12345,
      mixedWithNestedList: [],
      mixedWithNestedDict: {},
      dictCol: {},
      setCol: [],
      listOfInt: [],
    });

    // Row 3: decimal edge case -- MSD 8/9, forces the special
    // combination-field encoding (still fits in compact Bid64).
    realm.create("TargetRecord", { _id: 3, label: "target-three" });
    realm.create("AllTypesRecord", {
      _id: 3,
      intCol: 0,
      boolCol: true,
      stringCol: "decimal edge case: msd 8/9",
      dataCol: new Uint8Array([]).buffer,
      floatCol: 0,
      doubleCol: 0,
      decimalCol: BSON.Decimal128.fromString("89999999999999.5"),
      dateCol: new Date(0),
      uuidCol: new BSON.UUID(),
      objectIdCol: new BSON.ObjectId(),
      linkCol: null,
      linkList: [],
      mixedCol: 0,
      mixedWithNestedList: [],
      mixedWithNestedDict: {},
      dictCol: {},
      setCol: [],
      listOfInt: [],
    });

    // Row 4: 34-significant-digit decimal, forces the full 16-byte Bid128
    // storage (decimal64 tops out at 16 significant digits).
    realm.create("TargetRecord", { _id: 4, label: "target-four" });
    realm.create("AllTypesRecord", {
      _id: 4,
      intCol: 0,
      boolCol: true,
      stringCol: "decimal edge case: bid128",
      dataCol: new Uint8Array([]).buffer,
      floatCol: 0,
      doubleCol: 0,
      decimalCol: BSON.Decimal128.fromString("1.234567890123456789012345678901234"),
      dateCol: new Date(0),
      uuidCol: new BSON.UUID(),
      objectIdCol: new BSON.ObjectId(),
      linkCol: null,
      linkList: [],
      mixedCol: 0,
      mixedWithNestedList: [],
      mixedWithNestedDict: {},
      dictCol: {},
      setCol: [],
      listOfInt: [],
    });
  });

  console.log("Wrote", OUT_PATH, "size:", fs.statSync(OUT_PATH).size);
  realm.close();
})().catch((e) => {
  console.error("ERROR", e);
  process.exit(1);
});
