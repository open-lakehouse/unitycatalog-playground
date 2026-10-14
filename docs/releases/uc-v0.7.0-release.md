# What's new in Unity Catalog 0.7 — TL;DR

**In one sentence:** 0.7 turns Unity Catalog's Iceberg REST catalog into a full read/write, governed catalog that is on by default. It also makes the server production-ready: dropped managed data is now reclaimed, the server exposes health and metrics endpoints, multiple instances keep permissions in sync, and security is tightened across authorization, token exchange, AWS credential vending and local file access.

---

## Highlights

### 1. Iceberg REST catalog: read/write, governed, on by default

- **Native Iceberg tables.** You can create (including staged creates), commit, rename and drop native Iceberg tables through `/api/2.1/unity-catalog/iceberg`. Namespaces can be created and dropped, and their properties updated. Native Iceberg tables are **enabled by default** (`server.iceberg-table.enabled=true`).
[#1696](https://github.com/unitycatalog/unitycatalog/pull/1696) · [#1847](https://github.com/unitycatalog/unitycatalog/pull/1847) · [#1848](https://github.com/unitycatalog/unitycatalog/pull/1848) · [#1849](https://github.com/unitycatalog/unitycatalog/pull/1849) · [#1943](https://github.com/unitycatalog/unitycatalog/pull/1943)
- **Governed by UC privileges.** Each Iceberg endpoint now checks per-object UC privileges. In 0.6, every Iceberg endpoint required the metastore owner. Listings are filtered to what the caller can see.
[#1813](https://github.com/unitycatalog/unitycatalog/pull/1813) · [#1921](https://github.com/unitycatalog/unitycatalog/pull/1921)
- **Long-running clients keep their storage access.** A new `loadCredentials` endpoint plus advertised refresh endpoints let Iceberg clients renew the storage credentials UC vends.
[#1886](https://github.com/unitycatalog/unitycatalog/pull/1886)
- **Spec conformance and performance.** Errors are typed in Iceberg's vocabulary, existence checks return the spec's 204, an unknown warehouse gets a 404, and unrouted paths return parseable errors. Listings return every result and support pagination. `loadTable` supports ETag / `If-None-Match` and `snapshots=refs`. PyIceberg's `drop_table` and `purge_table` work now; before, UC rejected the `True` / `False` spelling PyIceberg sends. `purgeRequested` doesn't change what gets deleted: external table files stay, and managed storage goes through the normal cleanup. `reportMetrics` returns 204, and an unreadable metadata file returns a typed 500 without leaking its storage path. Table listing no longer re-resolves each table.
[#1797](https://github.com/unitycatalog/unitycatalog/pull/1797) · [#1836](https://github.com/unitycatalog/unitycatalog/pull/1836) · [#1842](https://github.com/unitycatalog/unitycatalog/pull/1842) · [#1843](https://github.com/unitycatalog/unitycatalog/pull/1843) · [#1801](https://github.com/unitycatalog/unitycatalog/pull/1801) · [#1845](https://github.com/unitycatalog/unitycatalog/pull/1845) · [#1791](https://github.com/unitycatalog/unitycatalog/pull/1791) · [#1878](https://github.com/unitycatalog/unitycatalog/pull/1878) · [#1853](https://github.com/unitycatalog/unitycatalog/pull/1853) · [#1844](https://github.com/unitycatalog/unitycatalog/pull/1844) · [#1890](https://github.com/unitycatalog/unitycatalog/pull/1890) · [#1775](https://github.com/unitycatalog/unitycatalog/pull/1775) · [#1799](https://github.com/unitycatalog/unitycatalog/pull/1799)
- **Tested end-to-end** with Spark 4.0/4.1 and Iceberg's `SparkCatalog`, including S3 credential vending against a fake S3 ([#1919](https://github.com/unitycatalog/unitycatalog/pull/1919), [#1922](https://github.com/unitycatalog/unitycatalog/pull/1922)). Server-side CRUD tests cover the REST endpoints directly ([#1814](https://github.com/unitycatalog/unitycatalog/pull/1814)).



### 2. Dropped managed data is now reclaimed

- Dropping a **managed table, managed volume, registered model or model version** queues a cleanup task in the same transaction. A background worker deletes the storage after a configurable delay (default **7 days**) on **local, S3, GCS and ADLS Gen2**. In 0.6, cloud storage was never deleted. Forced schema and catalog deletes queue the same cleanup for the tables and volumes they remove. With `server.authorization=enable`, paths waiting for cleanup can't be reused by new external tables, volumes or path credentials.
[#1857](https://github.com/unitycatalog/unitycatalog/pull/1857) · [#1858](https://github.com/unitycatalog/unitycatalog/pull/1858) · [#1865](https://github.com/unitycatalog/unitycatalog/pull/1865) · [#1870](https://github.com/unitycatalog/unitycatalog/pull/1870) · [#1872](https://github.com/unitycatalog/unitycatalog/pull/1872) · [#1895](https://github.com/unitycatalog/unitycatalog/pull/1895) · [#1915](https://github.com/unitycatalog/unitycatalog/pull/1915) · [#1917](https://github.com/unitycatalog/unitycatalog/pull/1917) · [#1904](https://github.com/unitycatalog/unitycatalog/pull/1904) · [#1936](https://github.com/unitycatalog/unitycatalog/pull/1936)
- Local cleanup never follows symbolic links: it removes a link, not what it points to ([#1976](https://github.com/unitycatalog/unitycatalog/pull/1976)).



### 3. Production readiness

- **Health and metrics:** `/livez`, `/readyz` and Prometheus `/metrics`, served on a dedicated, opt-in `--obs-port`. `/readyz` serves the cached result of a background database probe (`server.readiness.probe-interval`, default `PT5S`) and reports not-ready until the first check succeeds. New docs page: `docs/server/observability.md`.
[#1906](https://github.com/unitycatalog/unitycatalog/pull/1906)
- **Multi-instance deployments:** grants and revokes now propagate across server replicas when `server.authorization.policy-refresh=true`. It is off by default; when on, replicas reload policies every `policy-refresh-interval` (default `PT1M`). A denied request triggers a fresh policy check first.
[#1766](https://github.com/unitycatalog/unitycatalog/pull/1766) · [#1859](https://github.com/unitycatalog/unitycatalog/pull/1859)
- **One HikariCP pool** for Hibernate and Casbin, with `hibernate.hikari.maximumPoolSize` / `minimumIdle`.
[#1863](https://github.com/unitycatalog/unitycatalog/pull/1863)
- **Faster** `listTables`**:** properties, columns and view dependencies are batch-loaded instead of fetched per table.
[#1927](https://github.com/unitycatalog/unitycatalog/pull/1927)
- **Correctness fixes:**
  - Property values longer than 255 characters are supported ([#1824](https://github.com/unitycatalog/unitycatalog/pull/1824)).
  - Startup now waits for the client-facing port to bind, and the server shuts down and exits non-zero if it can't ([#1855](https://github.com/unitycatalog/unitycatalog/pull/1855)).
  - A missing volume returns 404 ([#1899](https://github.com/unitycatalog/unitycatalog/pull/1899)).
  - Creating a view or metric view without columns is rejected ([#1805](https://github.com/unitycatalog/unitycatalog/pull/1805)).



### 4. Security hardening

- **Authorization:**
  - Policies are tightened and made consistent across endpoints ([#1811](https://github.com/unitycatalog/unitycatalog/pull/1811)).
  - Request-body keys are authorized against the body the handler actually receives ([#1777](https://github.com/unitycatalog/unitycatalog/pull/1777)), with new cross-channel tests ([#1491](https://github.com/unitycatalog/unitycatalog/pull/1491)).
  - Policies and hierarchy links are cleared when a catalog or schema is force-deleted ([#1753](https://github.com/unitycatalog/unitycatalog/pull/1753)).
  - Errors are rendered in the dialect (UC / Delta / Iceberg) of the API that was called ([#1772](https://github.com/unitycatalog/unitycatalog/pull/1772)).
- **Token exchange:**
  - Principals are resolved from subject-token claims, so service principals can exchange tokens by `externalId`, which is now unique in `uc_users` ([#1691](https://github.com/unitycatalog/unitycatalog/pull/1691)).
  - The bootstrap `admin` principal is rejected ([#1780](https://github.com/unitycatalog/unitycatalog/pull/1780)).
- **AWS credential vending** now works with:
  - SSE-KMS buckets ([#1774](https://github.com/unitycatalog/unitycatalog/pull/1774))
  - GovCloud and China partitions ([#1794](https://github.com/unitycatalog/unitycatalog/pull/1794))
  - long paths, because session policies are smaller ([#1795](https://github.com/unitycatalog/unitycatalog/pull/1795))
  - S3-compatible STS services that reject wildcard IAM actions, because session policies now list explicit S3 actions ([#1817](https://github.com/unitycatalog/unitycatalog/pull/1817)). Custom S3 endpoints are still unsupported.
- **Bucket region discovery:** for a bucket with no configured `s3.region`, UC finds the region with an anonymous `HeadBucket`, caches it, and returns it to Iceberg clients ([#1935](https://github.com/unitycatalog/unitycatalog/pull/1935)).
- **Local file access:**
  - An external Iceberg table on local storage must sit under an external location or strictly under a root listed in the new `server.external-local-roots`; anything else gets a 403 before the server creates a directory. This applies even with authorization disabled. Malformed local `file:` URLs (an encoded `/` or NUL, an encoded dot segment, `..` above the root, a query or a fragment) get a 400 on every API ([#1973](https://github.com/unitycatalog/unitycatalog/pull/1973)).
  - Server-side local file I/O no longer follows symbolic links at or below a table's location, and storage cleanup deletes a link rather than its target ([#1976](https://github.com/unitycatalog/unitycatalog/pull/1976)).



### 5. Spark and Hadoop connectors

- **Bare cloud-path SQL with UC credentials.** Queries like `SELECT * FROM parquet.`s3://…``  and `INSERT OVERWRITE DIRECTORY` can use UC-vended credentials. This is opt-in: add `io.unitycatalog.spark.UCSparkSessionExtensions` to `spark.sql.extensions` and set `spark.sql.catalog.<catalog>.vendPathCredentials.enabled=true` (default `false`). The session's current catalog must be a `UCSingleCatalog` ([#1653](https://github.com/unitycatalog/unitycatalog/pull/1653)).
- **Bare-path queries no longer fail** with HTTP 400 when a UC catalog is current. No opt-in needed. Fixes [#1075](https://github.com/unitycatalog/unitycatalog/issues/1075) ([#1810](https://github.com/unitycatalog/unitycatalog/pull/1810), [#1875](https://github.com/unitycatalog/unitycatalog/pull/1875)).
- **Cleaner table metadata.** Vended credentials, Spark schema JSON and reserved V2 keys are no longer saved as table properties.
[#1789](https://github.com/unitycatalog/unitycatalog/pull/1789) · [#1830](https://github.com/unitycatalog/unitycatalog/pull/1830)
- **Writes fail early.** For `INSERT` / `UPDATE` / `DELETE` / `MERGE`, the connector requests read-write credentials up front and reports a denial at analysis time instead of falling back to read-only ([#1803](https://github.com/unitycatalog/unitycatalog/pull/1803)). This covers non-Delta tables, Delta < 4.3, and `deltaRestApi.enabled=false`. Catalog-managed Delta tables on the UC Delta API get their credentials from Delta's client and need [delta-io/delta#7518](https://github.com/delta-io/delta/pull/7518).
- **Other improvements:**
  - The Hadoop credential cache locks per key ([#1682](https://github.com/unitycatalog/unitycatalog/pull/1682)).
  - Jackson versions are aligned with each Spark line ([#1884](https://github.com/unitycatalog/unitycatalog/pull/1884)).



### 6. UC Delta API and managed Delta tables

- `loadTable` now returns `allowed-maintenance-operations` for managed and external tables ([#1812](https://github.com/unitycatalog/unitycatalog/pull/1812), [#1948](https://github.com/unitycatalog/unitycatalog/pull/1948)). Delta clients must honor this field before running maintenance on catalog-managed tables; Delta Lake 4.5 is expected to be the first release that does ([delta-io/delta#7564](https://github.com/delta-io/delta/pull/7564)).
- Commit retries are de-duplicated by file content ([#1778](https://github.com/unitycatalog/unitycatalog/pull/1778)), and lock contention gets a retryable `COMMIT_STATE_UNKNOWN` ([#1828](https://github.com/unitycatalog/unitycatalog/pull/1828)).
- The spec now spells out when to retry and when to rebase ([#1666](https://github.com/unitycatalog/unitycatalog/pull/1666)).
- `/delta/v1/config` no longer returns a literal `{catalog}` placeholder ([#1818](https://github.com/unitycatalog/unitycatalog/pull/1818)).



### 7. Unity Catalog AI (Python, versioned separately)

These are merged but not yet in a published release: `unitycatalog-ai` is still at 0.4.0.

- `DatabricksFunctionClient` Python UDFs can declare **service credentials and secrets** ([#1815](https://github.com/unitycatalog/unitycatalog/pull/1815), implements [#1816](https://github.com/unitycatalog/unitycatalog/issues/1816)).
- `unitycatalog-openai` no longer caps the `openai` version ([#1826](https://github.com/unitycatalog/unitycatalog/pull/1826)).



### Also in this release

- **Runtime upgrades:**
  - Armeria 1.41.1, Netty 4.2, Vert.x 4.5 ([#1883](https://github.com/unitycatalog/unitycatalog/pull/1883))
  - AWS SDK v2 2.54.18 ([#1879](https://github.com/unitycatalog/unitycatalog/pull/1879)), with the Apache HTTP client that Iceberg's `S3FileIO` needs for server-side metadata writes ([#1964](https://github.com/unitycatalog/unitycatalog/pull/1964))
  - Azure ([#1880](https://github.com/unitycatalog/unitycatalog/pull/1880)) and GCS / google-auth ([#1881](https://github.com/unitycatalog/unitycatalog/pull/1881))
  - auth libraries ([#1882](https://github.com/unitycatalog/unitycatalog/pull/1882))
- **UI** builds with **bun** instead of yarn ([#1732](https://github.com/unitycatalog/unitycatalog/pull/1732)).
- **Contributor docs:** `AGENTS.md`, `AI_POLICY.md` and `CODE_REVIEW.md` ([#1804](https://github.com/unitycatalog/unitycatalog/pull/1804), [#1862](https://github.com/unitycatalog/unitycatalog/pull/1862)).
- **Roadmap** updated through v1.0 ([#1760](https://github.com/unitycatalog/unitycatalog/pull/1760)).

---



## Heads-up when upgrading from 0.6

1. **Existing databases: run one** `ALTER TABLE`**.** `uc_properties.property_value` was widened ([#1824](https://github.com/unitycatalog/unitycatalog/pull/1824)), and `hbm2ddl=update` does not alter existing columns. The PostgreSQL, MySQL and H2 statements are in [docs/server/deployment.md](https://github.com/unitycatalog/unitycatalog/blob/main/docs/server/deployment.md).
2. **Dropping managed objects now deletes their storage.** This happens after `server.storage-cleanup.initial-delay` (default `P7D`), and the delay is not an undrop. In 0.6, cloud storage was left in place, local managed table and volume directories were deleted immediately, and model storage was never deleted ([#1872](https://github.com/unitycatalog/unitycatalog/pull/1872), [#1915](https://github.com/unitycatalog/unitycatalog/pull/1915), [#1917](https://github.com/unitycatalog/unitycatalog/pull/1917)).
3. **With** `server.authorization=enable`**:**
  - The metastore owner no longer bypasses schema update/delete, function delete, model and model-version delete, or path-credential vending. It needs ownership in the catalog → schema → object chain, or the matching privilege for path credentials. It can still delete catalogs, update or delete credentials and external locations, manage grants and users, and read everything ([#1811](https://github.com/unitycatalog/unitycatalog/pull/1811)).
  - Iceberg REST checks per-object privileges instead of requiring the metastore owner, so other users can use it with the right grants. The metastore owner alone can still read, but can't create, drop or rename tables or change namespaces ([#1813](https://github.com/unitycatalog/unitycatalog/pull/1813), [#1921](https://github.com/unitycatalog/unitycatalog/pull/1921)).
  - Requests with unusable bodies on body-authorized endpoints are rejected ([#1777](https://github.com/unitycatalog/unitycatalog/pull/1777)).
4. **Token exchange rejects the bootstrap** `admin` **principal** ([#1780](https://github.com/unitycatalog/unitycatalog/pull/1780)). Only the `/auth/tokens` exchange is affected.
5. **Library artifacts no longer ship a Log4j SLF4J binding** ([#1892](https://github.com/unitycatalog/unitycatalog/pull/1892)). `unitycatalog-client`, `unitycatalog-hadoop` and `unitycatalog-spark_`* now depend only on `slf4j-api`. If your app relied on the bundled binding, add `org.apache.logging.log4j:log4j-slf4j2-impl` (with `log4j-core`) or another SLF4J binding. The server and CLI are unchanged.
6. **Native Iceberg tables are on by default** ([#1943](https://github.com/unitycatalog/unitycatalog/pull/1943)). Set `server.iceberg-table.enabled=false` to keep Iceberg REST read-only. Existing native Iceberg tables stay readable.
7. **Iceberg REST responses follow the spec.** Error `type` values, 204s on HEAD, a 404 for an unknown warehouse, and JSON errors on unrouted paths ([#1797](https://github.com/unitycatalog/unitycatalog/pull/1797), [#1801](https://github.com/unitycatalog/unitycatalog/pull/1801), [#1842](https://github.com/unitycatalog/unitycatalog/pull/1842), [#1843](https://github.com/unitycatalog/unitycatalog/pull/1843), [#1836](https://github.com/unitycatalog/unitycatalog/pull/1836)).
8. **External Iceberg tables at local paths need an allowed root.** Creating one (or committing a staged create) at a local `file:` path returns 403 unless the path is under an external location or strictly under a directory listed in `server.external-local-roots` (unset by default). This applies even with authorization disabled. Cloud locations, managed tables and Delta are unchanged ([#1973](https://github.com/unitycatalog/unitycatalog/pull/1973)).
9. **Local tables behind symbolic links stop working.** An Iceberg REST table whose directory or `metadata/` is a symlink gets 403 on load and commit. A Delta table whose directory or `_delta_log/` is a symlink gets `COMMIT_STATE_UNKNOWN` ([#1976](https://github.com/unitycatalog/unitycatalog/pull/1976)).
10. **The server exits non-zero if it can't bind the client-facing port** ([#1855](https://github.com/unitycatalog/unitycatalog/pull/1855)). Before, it stayed half-up.
11. **Multi-replica deployments** should set `server.authorization.policy-refresh=true` ([#1766](https://github.com/unitycatalog/unitycatalog/pull/1766)).

---

## By the numbers

- **106 PRs:** 104 new in 0.7. [#1759](https://github.com/unitycatalog/unitycatalog/pull/1759) already shipped in 0.6.0 (cherry-picked as [#1784](https://github.com/unitycatalog/unitycatalog/pull/1784)), and [#1783](https://github.com/unitycatalog/unitycatalog/pull/1783) is an empty duplicate of it merged to `main`.
- About **335 files** changed (+30,869 / −14,433), with 28 PRs on the Iceberg REST catalog alone.
- **18 contributors plus 2 co-authors** (dataders, openinx).

