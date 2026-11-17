// Contract: IDs are finite integers or strings, immutable plain row objects.
// Returning the FIRST duplicate and the original object reference is intentional.
export function baseline(rows, ids) {
  return ids.map(id => rows.find(row => row.id === id));
}
export function indexed(rows, ids) {
  const first = new Map();
  for (const row of rows) if (!first.has(row.id)) first.set(row.id, row);
  return ids.map(id => first.get(id));
}
