import org.apache.spark.sql.{DataFrame, SparkSession, Encoders}
import org.apache.spark.sql.types.{StructType, StructField, StringType, IntegerType, BooleanType}
import io.delta.tables.{DeltaTable, DeltaTableBuilder}
import scala.collection.mutable.HashMap

// 1. Pets case class
case class Pets(uuid: String, name: String, age: Int, adopted: Boolean)

// 2. Convert a Seq[Pets] to a DataFrame using Encoders.product
def petsToDataFrame(pets: Seq[Pets], spark: SparkSession): DataFrame = {
  val encoder = Encoders.product[Pets]
  spark.createDataset(pets)(encoder).toDF()
}

// 3. Generate 50 unique Pets and return a grouped Iterator
def generatePets(batchSize: Int = 10): Iterator[Seq[Pets]] = {
  val names = List(
    "Luna", "Milo", "Bella", "Charlie", "Max",
    "Lucy", "Cooper", "Daisy", "Buddy", "Lily",
    "Rocky", "Molly", "Bear", "Lola", "Duke",
    "Sadie", "Tucker", "Zoe", "Oliver", "Stella"
  )
  val rng = new scala.util.Random
  Iterator.fill(50) {
    Pets(
      uuid    = java.util.UUID.randomUUID().toString,
      name    = names(rng.nextInt(names.length)),
      age     = rng.nextInt(15) + 1,
      adopted = rng.nextBoolean()
    )
  }.toSeq.grouped(batchSize)
}

// 4. Create a new Delta table, returning the builder for the caller to .execute()
// This doesn't work at the moment. The Catalog Managed Tables are new and the initial interface is SQL for create
def createDeltaTable(
  tableName:  String,
  schema:     StructType,
  properties: HashMap[String, String],
  spark:      SparkSession
): DeltaTableBuilder = {
  val builder = DeltaTable.createIfNotExists(spark)
    .tableName(tableName)
    .addColumns(schema)
  properties.foldLeft(builder) { case (b, (k, v)) => b.property(k, v) }
}

def createTableDDL(
  tableName:  String,
  schema:     StructType,
  properties: Map[String, String],
  spark:      SparkSession
): String = {
  val tblProperties = if (properties.nonEmpty) {
    val props = properties.map { case (k, v) => s"'$k' = '$v'" }.mkString(", ")
    s"TBLPROPERTIES ($props)"
  } else ""

  val ddl =
    s"""CREATE TABLE IF NOT EXISTS $tableName
       |(${schema.toDDL})
       |USING DELTA
       |$tblProperties
     """.stripMargin

  ddl
}

def createTableUsingSQL(
  tableName:  String,
  schema:     StructType,
  properties: Map[String, String],
  spark:      SparkSession
): DataFrame = {
  val tblProperties = if (properties.nonEmpty) {
    val props = properties.map { case (k, v) => s"'$k' = '$v'" }.mkString(", ")
    s"TBLPROPERTIES ($props)"
  } else ""

  val ddl =
    s"""CREATE TABLE IF NOT EXISTS $tableName
       |(${schema.toDDL})
       |USING DELTA
       |$tblProperties
     """.stripMargin

  spark.sql(ddl)
}
