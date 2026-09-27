/* Read-only check of Outline encrypted authentication fields. Never print tokens or keys. */
const { Client } = require("pg");
const crypto = require("node:crypto");

async function check() {
  const client = new Client({ connectionString: process.env.DATABASE_URL, ssl: false });
  try {
    await client.connect();
    await client.query("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY");
    const fields = {
      users: ["jwtSecret"],
      authentications: ["token", "refreshToken", "clientSecret"],
      user_authentications: ["accessToken", "refreshToken"],
      webhook_subscriptions: ["secret"],
      oauth_clients: ["clientSecret"],
    };
    const counts = [], affected = new Set();
    for (const [table, columns] of Object.entries(fields)) {
      for (const column of columns) {
        // Identifiers come exclusively from this component's fixed field list.
        const owner = table === "users" ? "id" : table === "user_authentications" ? '"userId"' : "NULL";
        const rows = (await client.query(`SELECT ${owner} AS owner, "${column}" AS value
          FROM "${table}" WHERE "${column}" IS NOT NULL`)).rows;
        let valid = 0, failed = 0;
        for (const row of rows) {
          try {
            const value = row.value;
            const decipher = crypto.createDecipheriv("aes-256-cbc",
              Buffer.from(process.env.SECRET_KEY, "hex"), value.subarray(0, 16));
            JSON.parse(decipher.update(value.subarray(16), undefined, "utf8") + decipher.final("utf8"));
            valid++;
          } catch (_) {
            failed++;
            if (row.owner) affected.add(row.owner);
          }
        }
        counts.push({ table, column, valid, failed });
      }
    }
    const users = affected.size ? (await client.query(
      'SELECT id, name FROM users WHERE id = ANY($1::uuid[])', [[...affected]])).rows : [];
    await client.query("COMMIT");
    const ok = counts.every(field => field.failed === 0);
    console.log(JSON.stringify({ ok, fields: counts, affected_users: users }));
    process.exitCode = ok ? 0 : 1;
  } finally {
    await client.end();
  }
}
check().catch(() => {
  console.log(JSON.stringify({ ok: false, error: "Outline authentication diagnostic could not complete" }));
  process.exitCode = 2;
});
