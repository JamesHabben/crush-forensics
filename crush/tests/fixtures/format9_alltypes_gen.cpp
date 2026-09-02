// Generates a Realm file format 9 (pre-Cluster) fixture exercising every old
// ColumnType, using realm-core v5.23.9's own public API. Values are authored
// here so a reader can be checked against what was actually written.
#include <realm.hpp>
#include <realm/descriptor.hpp>
#include <realm/group_shared.hpp>
#include <string>
#include <cstdio>

using namespace realm;

static std::string rep(const char* s, size_t n) {
    std::string out;
    while (out.size() < n) out += s;
    out.resize(n);
    return out;
}

int main(int argc, char** argv) {
    const char* path = argc > 1 ? argv[1] : "format9_alltypes.realm";
    std::remove(path);
    { std::string l(path); l += ".lock"; std::remove(l.c_str()); }
    SharedGroup sg(path);
    WriteTransaction wt(sg);
    Group& g = wt.get_group();

    // ---- link target table -------------------------------------------------
    TableRef target = g.add_table("class_Target");
    target->add_column(type_String, "name");
    target->add_empty_row(3);
    target->set_string(0, 0, "TARGET_ZERO");
    target->set_string(0, 1, "TARGET_ONE");
    target->set_string(0, 2, "TARGET_TWO");

    // ---- every-type table --------------------------------------------------
    TableRef t = g.add_table("class_AllTypes");
    size_t c_int   = t->add_column(type_Int,         "col_int");
    size_t c_bool  = t->add_column(type_Bool,        "col_bool");
    size_t c_str   = t->add_column(type_String,      "col_string_short");
    size_t c_med   = t->add_column(type_String,      "col_string_medium");
    size_t c_big   = t->add_column(type_String,      "col_string_big");
    size_t c_bin   = t->add_column(type_Binary,      "col_binary");
    DescriptorRef sub;
    size_t c_sub   = t->add_column(type_Table,       "col_subtable", &sub);
    sub->add_column(type_String, "sub_name");
    sub->add_column(type_Int,    "sub_value");
    size_t c_mix   = t->add_column(type_Mixed,       "col_mixed");
    size_t c_odt   = t->add_column(type_OldDateTime, "col_olddatetime");
    size_t c_ts    = t->add_column(type_Timestamp,   "col_timestamp");
    size_t c_flt   = t->add_column(type_Float,       "col_float");
    size_t c_dbl   = t->add_column(type_Double,      "col_double");
    size_t c_lnk   = t->add_column_link(type_Link,     "col_link",     *target);
    size_t c_lls   = t->add_column_link(type_LinkList, "col_linklist", *target);

    const size_t NROWS = 9;
    t->add_empty_row(NROWS);

    // deliberately awkward integers, including negatives (Mixed sign encoding)
    const int64_t ints[NROWS] = {0, 1, -1, 42, -42, 2147483647LL, -2147483648LL,
                                 9007199254740993LL, -9007199254740993LL};
    for (size_t r = 0; r < NROWS; ++r) {
        t->set_int(c_int, r, ints[r]);
        t->set_bool(c_bool, r, (r % 2) == 0);
        t->set_string(c_str, r, StringData(("SHORT_" + std::to_string(r)).c_str()));
        std::string med = rep("MEDIUM_", 40 + r);   // 40..48 bytes -> ArrayStringLong (<=63)
        std::string big = rep("BIGBLOB_", 70000 + r);
        t->set_string(c_med, r, StringData(med));
        t->set_string(c_big, r, StringData(big));
        std::string b = "BINARY_" + std::to_string(r);
        t->set_binary(c_bin, r, BinaryData(b.data(), b.size()));
        t->set_olddatetime(c_odt, r, OldDateTime(1000000000LL + int64_t(r) * 86400));
        t->set_timestamp(c_ts, r, Timestamp(1600000000LL + int64_t(r) * 3600, int32_t(r) * 1000));
        t->set_float(c_flt, r, 1.5f * float(r) - 2.25f);
        t->set_double(c_dbl, r, 3.25 * double(r) - 7.125);
        t->set_link(c_lnk, r, r % 3);
        LinkViewRef lv = t->get_linklist(c_lls, r);
        for (size_t k = 0; k <= (r % 3); ++k) lv->add(k);
        TableRef st = t->get_subtable(c_sub, r);
        for (size_t k = 0; k < (r % 3); ++k) {
            st->add_empty_row(1);
            st->set_string(0, k, StringData(("SUB_" + std::to_string(r) + "_" + std::to_string(k)).c_str()));
            st->set_int(1, k, int64_t(r) * 100 + int64_t(k));
        }
    }

    // one Mixed row per Mixed subtype, so every type tag is exercised
    t->set_mixed(c_mix, 0, Mixed(int64_t(0)));
    t->set_mixed(c_mix, 1, Mixed(int64_t(123456789)));
    t->set_mixed(c_mix, 2, Mixed(int64_t(-987654321)));      // negative sign encoding
    t->set_mixed(c_mix, 3, Mixed(true));
    t->set_mixed(c_mix, 4, Mixed(StringData("MIXED_STRING_VALUE")));
    std::string mb = "MIXED_BINARY";
    t->set_mixed(c_mix, 5, Mixed(BinaryData(mb.data(), mb.size())));
    t->set_mixed(c_mix, 6, Mixed(float(2.5f)));
    t->set_mixed(c_mix, 7, Mixed(double(-4.75)));
    t->set_mixed(c_mix, 8, Mixed(Timestamp(1700000000LL, 500)));

    // ---- StringEnum: low-cardinality string column, then optimize ----------
    TableRef e = g.add_table("class_EnumStrings");
    e->add_column(type_String, "enum_value");
    e->add_column(type_Int, "row_id");
    e->add_empty_row(12);
    const char* pool[3] = {"ALPHA", "BETA", "GAMMA"};
    for (size_t r = 0; r < 12; ++r) {
        e->set_string(0, r, StringData(pool[r % 3]));
        e->set_int(1, r, int64_t(r));
    }
    e->optimize(true);   // forces col_type_String -> col_type_StringEnum

    wt.commit();
    std::printf("wrote %s\n", path);
    std::printf("  class_Target      3 rows\n");
    std::printf("  class_AllTypes    %zu rows, %zu columns\n", NROWS, t->get_column_count());
    std::printf("  class_EnumStrings 12 rows (optimize -> StringEnum)\n");
    return 0;
}
