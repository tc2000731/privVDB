import llm
from pymilvus import CollectionSchema, FieldSchema, DataType, connections, db, utility, Collection
import json
import logging
import numpy as np
import uuid
import desensitization
from types import SimpleNamespace
# logging.basicConfig(level=logging.INFO)


def desensitize_text(self, results, desensitizer):
    logging.info("results: ", results)
    print(results[0][0])
    return "QAQ"


class PrivVDB:

    def __init__(self, config):
        if config["text_dp_type"] == "santext":
            self.text_dp = desensitization.SanText(
                config=config["text_dp_config"])
        self.vdb = VDBHandler()

    def get_dp_text(self, AgentID: str, text, eps):
        if AgentID == "admin":
            print(1)
        return self.text_dp.desensitization(text, eps)

    def init_database(self):
        memory_id = FieldSchema(
            name="id",
            dtype=DataType.VARCHAR,
            max_length=200,
            is_primary=True,
        )
        agent_id = FieldSchema(
            name="playerId",
            dtype=DataType.VARCHAR,
            max_length=200,
            # The default value will be used if this field is left empty during data inserts or upserts.
        )
        embeddings = FieldSchema(
            name="values",
            dtype=DataType.FLOAT_VECTOR,
            dim=1536
        )
        private_text = FieldSchema(
            name="private_text",
            dtype=DataType.VARCHAR,
            max_length=2048,
            description="private_text"
        )

        schema = CollectionSchema(
            fields=[memory_id, embeddings, agent_id, private_text],
            description="test_table",
            enable_dynamic_field=True
        )
        data = {}
        data["database_name"] = "test_db"
        data["table_name"] = "test_table"
        data["schema"] = schema
        f_n = "values"
        data["reset"] = True
        index_params = {
            "metric_type": "L2",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 256}
        }
        fake_index = SimpleNamespace()
        setattr(fake_index, "field_name", f_n)
        setattr(fake_index, "params", index_params)
        data["indexes"] = [fake_index]
        self.vdb.create_table(data)

    def search_text(self, text):
        embeds = llm.get_embeddings(text)["embeddings"]
        logging.info(len(embeds))
        data = {}
        data["database_name"] = "test_db"
        data["table_name"] = "test_table"

        data["search_params"] = {
            "metric_type": "L2",
            "params": {"nprobe": 4}
        }
        data["topK"] = 7
        data["embedding"] = embeds
        data["search_field"] = "values"
        r = self.vdb.query_Data(data)["result"]
        logging.info(r)
        res_text = [x.to_dict()["entity"]["private_text"] for x in r[0]]
        score = [x.to_dict()["distance"] for x in r[0]]
        return res_text, score

    def insert_text(self, text):
        embeds = llm.get_embeddings(text)["embeddings"]
        data = {}
        data["database_name"] = "test_db"
        data["table_name"] = "test_table"
        data_id = str(uuid.uuid4())
        upsert_data = [[data_id], [embeds], [
            "agent1"], [text]]
        data["upsert_data"] = upsert_data
        self.vdb.upsert_Data(data)
        return embeds


class VDBHandler:

    def __init__(self, host="localhost", port=19530):
        connections.connect(host="localhost", port=19530)

    def alive(self):
        return "Ok"

    def print_records(self, database_name, table_name=None):
        if database_name not in db.list_database():
            logging.error(database_name+" not in milvus!")
            return
        logging.info("print database:"+database_name)
        db.using_database(database_name)
        for c in utility.list_collections():
            if table_name is not None and table_name != c:
                continue
            t = Collection(c)
            t.flush()
            t.load()
            num = t.num_entities  # 获取元素数量
            logging.info("\nCollection :  "+c+"("+str(num)+" records)\n")
            em = t.is_empty

            if not em:
                result = t.query(expr="", output_fields=[
                    "*"], limit=num)  # 查询所有元素的所有属性
                logging.info(result)  # 打印结果
            else:
                logging.warning("EMPTY!")

    def upsert_Data(self, data):
        database_name = data["database_name"]
        table_name = data["table_name"]
        db.using_database(database_name)
        table = Collection(table_name)
        upsert_data = data["upsert_data"]
        # logging.info(upsert_data)
        mr = table.insert(upsert_data)
        response = {"message": "Data upsert successfully :)", "mr": mr}
        logging.info(response)
        return response

    def delete_Data(self, data):
        database_name = data["database_name"]
        table_name = data["table_name"]
        db.using_database(database_name)
        if "delete_all" in data.keys() and data["delete_all"] == True:
            data["reset"] = True
            table = Collection(table_name)
            data["indexes"] = table.indexes
            data["schema"] = table.schema
            # utility.drop_collection(table_name)
            self.create_table(data)
        else:
            table = Collection(table_name)
            table.delete("id = "+str(data["delete_id"]))
        response = {"message": "Data delete successfully :)"}
        logging.info(response)
        return response

    def query_Data(self, data):
        table_name = data["table_name"]
        database_name = data["database_name"]
        db.using_database(database_name)
        table = Collection(table_name)
        table.flush()
        table.load()
        expr = data["expr"] if "expr" in data.keys() else None
        search_params = data["search_params"]
        res = table.search(data=[data["embedding"]], limit=data["topK"],
                           param=search_params, anns_field=data["search_field"], consistency_level="Strong", expr=expr, output_fields=["private_text"])
        response = {"message": "search success", "result": res}
        logging.info(response)
        return response

    def create_table(self, config):
        database_name = config["database_name"]
        table_name = config["table_name"]
        if database_name not in db.list_database():
            db.create_database(database_name)
        db.using_database(database_name)
        if config.get("reset", False):
            utility.drop_collection(table_name)
            print("Successfully deleted collections")
        schema = config["schema"]
        if not utility.has_collection(table_name):
            c = Collection(
                name=table_name,
                schema=schema,
            )
            for index in config["indexes"]:
                c = Collection(table_name)
                c.create_index(field_name=index.field_name,
                               index_params=index.params)
            print('Successfully created collections')
        else:
            if not schema == Collection(table_name).schema:
                print("schema not equal!!!")
        print(utility.has_collection(table_name))


if __name__ == "__main__":
    # vdb = VDBHandeler()
    pass
