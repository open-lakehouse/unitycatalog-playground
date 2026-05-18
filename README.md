# unitycatalog-playground
This project makes use of the open source Unity Catalog project and introduces a full notebook environment for simplifying how you work with UC OSS.

---

## Build the Docker Environment

```bash
docker build -t marimo-spark .
```

> note: If you need to build this with a custom pip proxy, 
> you can use the --build-arg PIP_INDEX_URL=https://pypi-proxy.your-company.com/simple

## Run the Environment
```bash
docker compose up
```
You will see the `marimo` and `unitycatalog` containers come up.
<img width="683" height="296" alt="Screenshot 2026-02-25 at 5 39 34 PM" src="https://github.com/user-attachments/assets/ae7d8393-3bdc-4d70-9630-ac2b875b5ba4" />

In order to run the full notebook environment, copy the ➜  URL: http://0.0.0.0:2718?access_token=TOKEN and run it in your favorite browser.

## Using the Notebook
Once you're in the notebook environment (marimo), you simply need to **run** each cell in order (you can skip the markdown cells since they are just there to add additional context). 

You'll see a view like the one below:

<img width="1008" height="1184" alt="Screenshot 2026-02-25 at 5 40 31 PM" src="https://github.com/user-attachments/assets/14a50e3f-f4dc-4b69-9ee4-3edb54e8e48e"/>

<br>
<br>
When you are finished with the notebook example, you can simple **tear down the environment**. 

Congrats. You've now officially written a Catalog Managed Table using Delta Lake and Unity Catalog.

## Tear Down the Environment

To stop and remove all containers, networks, and persistent volumes:

```bash
docker compose down --volumes --remove-orphans
```

## Catalog Managed Tables — Python Helpers

The helper module at [`delta/python/catalog-managed.py`](delta/python/catalog-managed.py) provides a set of reusable utilities for creating and populating catalog-managed Delta tables via PySpark. These same helpers are used interactively in the [`marimo-playground/notebooks/unitycatalog-delta.py`](marimo-playground/notebooks/unitycatalog-delta.py) notebook.

### `Pets` dataclass

A simple dataclass representing a rescue animal record.

```python
@dataclass
class Pets:
    uuid: str    # unique identifier
    name: str    # pet name
    age: int     # age in years
    adopted: bool
```

---

### `generate_pets(batch_size=10, total=100)`

Generates `total` random `Pets` records and yields them in batches of `batch_size`.

```python
pets = generate_pets(batch_size=10, total=100)

first_batch = next(pets)        # list[Pets] with 10 records
for batch in pets:              # iterate remaining batches
    print(batch)
```

---

### `pets_to_dataframe(pets, spark)`

Converts a `list[Pets]` batch into a Spark `DataFrame` with an explicit schema.

```python
df = pets_to_dataframe(first_batch, spark)
df.show()
```

Schema:

| column    | type    | nullable |
|-----------|---------|----------|
| `uuid`    | string  | no       |
| `name`    | string  | no       |
| `age`     | integer | no       |
| `adopted` | boolean | no       |

---

### `create_table_ddl(table_name, schema, properties)`

Builds a `CREATE TABLE IF NOT EXISTS ... USING DELTA` DDL string from a `StructType` schema and an optional `dict` of `TBLPROPERTIES`.

```python
props = {"delta.feature.catalogManaged": "supported"}
ddl = create_table_ddl("sanctuary.pets", df.schema, props)
print(ddl)
```

---

### `create_table_using_sql(table_name, schema, properties, spark)`

Executes the DDL produced by `create_table_ddl` via `spark.sql`. Returns an empty `DataFrame` on success.

```python
create_table_using_sql("sanctuary.pets", df.schema, props, spark)
```

---

### End-to-end example

The following mirrors the flow in the [`unitycatalog-delta`](marimo-playground/notebooks/unitycatalog-delta.py) notebook:

```python
# 1. Create the schema
spark.sql("CREATE SCHEMA IF NOT EXISTS unity.sanctuary")

# 2. Generate pets
pets = generate_pets(batch_size=10, total=100)
first_batch = next(pets)

# 3. Derive the schema from the first batch
df = pets_to_dataframe(first_batch, spark)
props = {"delta.feature.catalogManaged": "supported"}

# 4. Create the table
create_table_using_sql("sanctuary.pets", df.schema, props, spark)

# 5. Write the first batch
df.write.format("delta").mode("append").saveAsTable("sanctuary.pets")

# 6. Write remaining batches
for batch in pets:
    pets_to_dataframe(batch, spark).write.format("delta").mode("append").saveAsTable("sanctuary.pets")

# 7. Verify
spark.sql("SELECT COUNT(*) AS total FROM sanctuary.pets").show()
```
