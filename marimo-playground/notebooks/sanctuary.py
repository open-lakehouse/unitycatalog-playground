"""Shared animal-sanctuary data for the playground notebooks.

Every notebook builds its rows from the same seeded pet roster, whichever
engine writes them: Delta on Spark 4.2, Iceberg on Spark 4.1, or PyIceberg
with no JVM. A pet's `uuid` and attributes are therefore identical in every
table, so Delta and Iceberg tables join on it, e.g. Delta
`unity.sanctuary.pets.uuid` = Iceberg `unity.iceberg_spark.adoptions.pet_uuid`.

Generation is deterministic (fixed seed and `AS_OF` time) and prefix-stable:
`roster(120)[:100] == roster(100)`, so extra pets extend the roster without
changing the earlier ones.

Only the standard library is imported here; the Spark helpers import PySpark
when called, so PyIceberg notebooks can use this module without it.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Iterable, Iterator, Sequence, get_type_hints

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = [
    "AS_OF",
    "PET_COLUMNS",
    "PET_NAMES",
    "ROSTER_SIZE",
    "SEED",
    "SHELTERS",
    "SPECIES",
    "Adoption",
    "Pets",
    "adopt",
    "adoptions",
    "generate_pets",
    "pets_to_dataframe",
    "roster",
    "rows",
    "to_spark_dataframe",
]

SEED = 2026
ROSTER_SIZE = 100
# Generated timestamps fall before this instant, so reruns don't drift with the clock.
AS_OF = datetime(2026, 10, 1, tzinfo=timezone.utc)
INTAKE_WINDOW_DAYS = 120

PET_NAMES = (
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
)
SPECIES = ("dog", "cat", "rabbit", "parrot", "hamster")
SHELTERS = ("north", "south", "east", "west")
# Base adoption fee (USD) by species; each adoption varies it by +/-20%.
BASE_FEES = {"dog": 250.0, "cat": 150.0, "rabbit": 90.0, "parrot": 300.0, "hamster": 25.0}

# The Delta table `unity.sanctuary.pets` stores this projection of `Pets`.
PET_COLUMNS = ("uuid", "name", "age", "adopted")


@dataclass(frozen=True)
class Pets:
    """One animal in the sanctuary roster."""

    uuid: str
    name: str
    age: int
    adopted: bool
    species: str
    shelter: str
    intake_at: datetime


@dataclass(frozen=True)
class Adoption:
    """One adoption event, keyed back to the roster by `pet_uuid`."""

    adoption_id: int = field(metadata={"spark_type": "LongType"})
    pet_uuid: str
    pet_name: str
    species: str
    shelter: str
    adopted_at: datetime
    fee: float


def roster(total: int = ROSTER_SIZE, seed: int = SEED) -> list[Pets]:
    """The first `total` pets of the roster for `seed`."""
    rng = random.Random(seed)
    return [_next_pet(rng) for _ in range(total)]


def _next_pet(rng: random.Random) -> Pets:
    return Pets(
        uuid=str(uuid.UUID(int=rng.getrandbits(128), version=4)),
        name=rng.choice(PET_NAMES),
        age=rng.randint(1, 15),
        adopted=rng.random() < 0.5,
        species=rng.choice(SPECIES),
        shelter=rng.choice(SHELTERS),
        intake_at=AS_OF - timedelta(seconds=rng.randrange(INTAKE_WINDOW_DAYS * 86_400)),
    )


def generate_pets(
    batch_size: int = 10, total: int = ROSTER_SIZE, seed: int = SEED
) -> Iterator[list[Pets]]:
    """The roster in batches of `batch_size` (one batch per commit in the Delta notebook)."""
    pets = roster(total, seed)
    for i in range(0, len(pets), batch_size):
        yield pets[i : i + batch_size]


def adopt(pet: Pets, adoption_id: int, seed: int = SEED) -> Adoption:
    """The adoption of `pet`, between its intake and `AS_OF`.

    Seeded per pet, so the same pet always gets the same date and fee
    regardless of which other pets are adopted alongside it.
    """
    rng = random.Random(f"{seed}:{pet.uuid}")
    return Adoption(
        adoption_id=adoption_id,
        pet_uuid=pet.uuid,
        pet_name=pet.name,
        species=pet.species,
        shelter=pet.shelter,
        adopted_at=pet.intake_at + (AS_OF - pet.intake_at) * rng.uniform(0.05, 1.0),
        fee=round(BASE_FEES[pet.species] * rng.uniform(0.8, 1.2), 2),
    )


def adoptions(pets: Iterable[Pets], start_id: int = 1, seed: int = SEED) -> list[Adoption]:
    """One adoption per pet with `adopted=True`, numbered from `start_id`."""
    adopted = (pet for pet in pets if pet.adopted)
    return [adopt(pet, adoption_id, seed) for adoption_id, pet in enumerate(adopted, start_id)]


def rows(records: Iterable[Pets | Adoption], columns: Sequence[str] | None = None) -> list[dict]:
    """Records as plain dicts (e.g. for `pyarrow.Table.from_pylist`), optionally projected."""
    out = []
    for record in records:
        names = columns or [f.name for f in fields(record)]
        out.append({name: getattr(record, name) for name in names})
    return out


def to_spark_dataframe(
    records: Sequence[Pets | Adoption],
    spark: SparkSession,
    columns: Sequence[str] | None = None,
) -> DataFrame:
    """Records as a Spark DataFrame with a non-nullable schema derived from the dataclass."""
    from pyspark.sql import types as T

    if not records:
        raise ValueError("to_spark_dataframe needs at least one record to infer the schema")
    record_type = type(records[0])
    by_name = {f.name: f for f in fields(record_type)}
    hints = get_type_hints(record_type)
    default_types = {
        str: "StringType",
        int: "IntegerType",
        bool: "BooleanType",
        float: "DoubleType",
        datetime: "TimestampType",
    }
    names = list(columns or by_name)
    schema = T.StructType([
        T.StructField(
            name,
            getattr(T, by_name[name].metadata.get("spark_type", default_types[hints[name]]))(),
            nullable=False,
        )
        for name in names
    ])
    data = [tuple(getattr(record, name) for name in names) for record in records]
    return spark.createDataFrame(data, schema=schema)


def pets_to_dataframe(pets: Sequence[Pets], spark: SparkSession) -> DataFrame:
    """Pets as a DataFrame in the `unity.sanctuary.pets` Delta shape (`PET_COLUMNS`)."""
    return to_spark_dataframe(pets, spark, PET_COLUMNS)
