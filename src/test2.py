import random
from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
)
connections.connect("default", host="localhost", port="19530")
Collection("hello_milvus").drop()
fields = [
    FieldSchema(name="pk", dtype=DataType.INT64,
                is_primary=True, auto_id=False),
    FieldSchema(name="random", dtype=DataType.DOUBLE),
    FieldSchema(name="embeddings", dtype=DataType.FLOAT_VECTOR, dim=8)
]
schema = CollectionSchema(
    fields, "hello_milvus is the simplest demo to introduce the APIs")
hello_milvus = Collection("hello_milvus", schema)
sz = 1
entities = [
    [i for i in range(sz)],  # field pk
    [float(random.randrange(-20, -10)) for _ in range(sz)],  # field random
    [[random.random() for _ in range(8)]
     for _ in range(sz)],  # field embeddings
]
insert_result = hello_milvus.insert(entities)
# After final entity is inserted, it is best to call flush to have no growing segments left in memory
hello_milvus.flush()

index = {
    "index_type": "IVF_FLAT",
    "metric_type": "L2",
    "params": {"nlist": 128},
}
hello_milvus.create_index("embeddings", index)
hello_milvus.load()
vectors_to_search = entities[-1][-2:]
search_params = {
    "metric_type": "L2",
    "params": {"nprobe": 10},
}
result = hello_milvus.search(
    vectors_to_search, "embeddings", search_params, limit=3, output_fields=["random"])
print(result)
result = hello_milvus.query(
    expr="random > -14", output_fields=["random", "embeddings"])
print(result)