// Source-table -> Firestore layout. See SCHEMA.md.
// kind 'doc'  : one document per row, id = id(row, index)
// kind 'chunk': docs chunk_0001.. with {chunk, rows, count, table}; `per` = rows per chunk
export const MAX_DOC_BYTES = 800 * 1024;

const k = (...cols) => (r) => cols.map((c) => r[c]).join('_');
const n = (r, i) => String(i + 1);

export const TABLES = {
  stores: { kind: 'doc', id: k('store_id'), num: ['size_sqft', 'stock_capacity_units'] },
  area_managers: {
    kind: 'doc', id: k('area_manager_id'), num: ['max_alerts_per_week'],
    // extra: parsed store list so the page need not split the string
    extra: (r) => ({ store_ids: r.stores.split(',').map((s) => s.trim()).filter(Boolean) }),
  },
  items: { kind: 'doc', id: k('sku_id'), num: ['mrp', 'cost_price', 'is_core_style', 'is_packaging'] },
  salespeople: { kind: 'doc', id: k('salesperson_id'), num: [] },
  calendar: { kind: 'doc', id: k('date', 'state'), num: ['is_wedding_date'] },
  rules: { kind: 'doc', id: n, num: [] },
  min_display: { kind: 'doc', id: k('tier', 'category'), num: ['min_display_units'] },
  lead_times: { kind: 'doc', id: n, num: ['days'] },
  flagship_protected: { kind: 'doc', id: k('store_id', 'rank'), num: ['rank'] },
  warehouse_inbound: { kind: 'doc', id: n, num: ['qty'] },
  stock_snapshot: { kind: 'doc', id: k('location_id', 'sku_id'), num: ['on_hand', 'in_transit'] },
  data_dictionary: { kind: 'doc', id: k('tab', 'column'), num: [] },
  // Big tables: rows per chunk chosen so the largest chunk stays ~ 550-700 KB (measured by the dry run).
  stock_weekly: { kind: 'chunk', per: 5000, num: ['closing_on_hand', 'days_in_stock'] },
  bills: { kind: 'chunk', per: 5000, num: [] },
  bill_lines: { kind: 'chunk', per: 6000, num: ['qty', 'mrp', 'selling_price'] },
  roster_daily: { kind: 'chunk', per: 5000, num: [] },
  footfall_daily: { kind: 'chunk', per: 8000, num: ['footfall'] },
};
