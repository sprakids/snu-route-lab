// Cloudflare cursor metrics include SQLite's billable reads/writes. Test adapters
// provide a conservative local approximation; these are not account-wide metrics.
export function meteredSql(sql,onCost){
 return {exec(query,...args){
  const cursor=sql.exec(query,...args),rows=cursor.toArray();
  onCost(Number(cursor.rowsRead)||0,Number(cursor.rowsWritten)||0);
  return {toArray:()=>rows,[Symbol.iterator]:()=>rows[Symbol.iterator]()};
 }};
}
