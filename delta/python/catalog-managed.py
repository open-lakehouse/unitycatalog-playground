import uuid
import random
from dataclasses import dataclass, fields
from typing import Iterator

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import (
    StructType, StructField,
    StringType, IntegerType, BooleanType,
)
from delta.tables import DeltaTable


# 1. Pets dataclass
@dataclass
class Pets:
    uuid: str
    name: str
    age: int
    adopted: bool


# 2. Convert a list of Pets to a DataFrame
def pets_to_dataframe(pets: list[Pets], spark: SparkSession) -> DataFrame:
    rows = [
        (p.uuid, p.name, p.age, p.adopted)
        for p in pets
    ]
    schema = StructType([
        StructField("uuid",    StringType(),  nullable=False),
        StructField("name",    StringType(),  nullable=False),
        StructField("age",     IntegerType(), nullable=False),
        StructField("adopted", BooleanType(), nullable=False),
    ])
    return spark.createDataFrame(rows, schema=schema)


# 3. Generate 50 unique Pets and return a batched iterator
def generate_pets(batch_size: int = 10, total: int = 100) -> Iterator[list[Pets]]:
    names = [
        "Luna", "Milo", "Bella", "Charlie", "Max",
        "Lucy", "Cooper", "Daisy", "Buddy", "Lily",
        "Rocky", "Molly", "Bear", "Lola", "Duke",
        "Sadie", "Tucker", "Zoe", "Oliver", "Stella",
        "Archie", "Rosie", "Leo", "Cleo", "Finn",
        "Nova", "Jasper", "Willow", "Atlas", "Ivy",
        "Theo", "Ruby", "Gus", "Nala", "Remy",
        "Pepper", "Beau", "Coco", "Arlo", "Hazel",
        "Scout", "Freya", "Hugo", "Maple", "Rufus",
        "Juniper", "Otis", "Penny", "Bentley", "Sage",
        "Winston", "Piper", "Clover", "Dexter", "Wren",
        "Biscuit", "Tilly", "Monty", "Fern", "Chester",
        "Poppy", "Bruno", "Skye", "Ziggy", "Opal",
        "Roux", "Nimbus", "Dottie", "Cosmo", "Waffles",
    ]
    pets = [
        Pets(
            uuid=str(uuid.uuid4()),
            name=random.choice(names),
            age=random.randint(1, 15),
            adopted=random.choice([True, False]),
        )
        for _ in range(total)
    ]
    for i in range(0, len(pets), batch_size):
        yield pets[i : i + batch_size]


# 4. Create a Delta table using the DeltaTable builder
def create_delta_table(
    table_name: str,
    schema: StructType,
    properties: dict[str, str],
    spark: SparkSession,
) -> DeltaTable:
    """
    Create a Delta table using the DeltaTable builder
    note: this doesn't work yet. We need to wait for the DeltaTable support to be added. Use the SQL version for now.
    """
    builder = DeltaTable.createIfNotExists(spark).tableName(table_name).addColumns(schema)
    for k, v in properties.items():
        builder = builder.property(k, v)
    return builder.execute()


# 5. Build a CREATE TABLE DDL string
def create_table_ddl(
    table_name: str,
    schema: StructType,
    properties: dict[str, str],
) -> str:
    tbl_properties = ""
    if properties:
        props = ", ".join(f"'{k}' = '{v}'" for k, v in properties.items())
        tbl_properties = f"TBLPROPERTIES ({props})"

    col_defs = ", ".join(
        f"{field.name} {field.dataType.simpleString().upper()} {'NOT NULL' if not field.nullable else ''}"
        for field in schema.fields
    )
    return (
        f"CREATE TABLE IF NOT EXISTS {table_name}\n"
        f"({col_defs})\n"
        f"USING DELTA\n"
        f"{tbl_properties}"
    ).strip()


# 6. Create a Delta table by executing DDL via spark.sql
def create_table_using_sql(
    table_name: str,
    schema: StructType,
    properties: dict[str, str],
    spark: SparkSession,
) -> DataFrame:
    ddl = create_table_ddl(table_name, schema, properties, spark)
    return spark.sql(ddl)
