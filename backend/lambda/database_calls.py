from lambda_config import config
import base64
import json
import os
import sqlalchemy
from google.cloud import secretmanager

class DatabaseCalls():

    def get_secret(self):
        print('grabbing secret')
        
        client = secretmanager.SecretManagerServiceClient()
        secret_name = "deepcite_db"
        project_id = "deepcite-306405"

        request = {"name": f"projects/{project_id}/secrets/{secret_name}/versions/latest"}
        response = client.access_secret_version(request)
        secret_string = response.payload.data.decode("UTF-8")

        return {'password':secret_string, 'username': 'postgres', 'host': '35.226.116.208', 'dbInstanceIdentifier': 'postgres', 'port': 5432}

    def __init__(self):
        secret = self.get_secret()
        self.conn = None

        db_config = {
            "pool_size": 1,
            "max_overflow": 2,
            "pool_timeout": 30,  # 30 seconds
            "pool_recycle": 540,  # 30 minutes
        }

        db_socket_dir = os.environ.get("DB_SOCKET_DIR", "/cloudsql")
        cloud_sql_connection_name = 'deepcite-306405:us-central1:deepcite'#os.environ["CLOUD_SQL_CONNECTION_NAME"]

        pool = sqlalchemy.create_engine(

            sqlalchemy.engine.url.URL(
                drivername="postgresql+pg8000",
                username=secret['username'],  # e.g. "my-database-user"
                password=secret['password'],  # e.g. "my-database-password"
                database=secret['dbInstanceIdentifier'],  # e.g. "my-database-name"
                query={
                    "unix_sock": "{}/{}/.s.PGSQL.5432".format(
                        db_socket_dir,  # e.g. "/cloudsql"
                        cloud_sql_connection_name)  # i.e "<PROJECT-NAME>:<INSTANCE-REGION>:<INSTANCE-NAME>"
                }
            ),
            **db_config
        )

        self.conn = pool.connect()

    def grab_deepcite_entry(self, id):
        try:
            with self.conn.connect() as cur:

                responses = cur.execute(f"SELECT response FROM deepcite_call where id = '{id}'").fetchall() #potentially this could just be a search by source claim and link and run for everything
                responses = [res[0] for res in responses]
        except Exception as e:
            print("ERROR: Unexpected error: Could not select from database instance.")
            print(e)
            responses = []
        print("Deepcite entry responses:", responses)
        return responses

    def record_call(self, new_submission, base_id, user_id, stage, status_code, response, time_elapsed, versions):
        try:
            with self.conn.connect() as cur:
                if new_submission:
                    cur.execute("INSERT INTO deepcite_call (id,user_id,stage,status_code,response,response_time_elapsed,current_versions) VALUES (%s, %s, %s, %s, %s, %s, %s)", (base_id, user_id, stage, status_code, json.dumps(response), time_elapsed, json.dumps(versions)))
                else:
                    cur.execute("INSERT INTO deepcite_retrieval (id,user_id,stage,status_code,response_time_elapsed,current_versions) VALUES (%s, %s, %s, %s, %s, %s)", (base_id, user_id, stage, status_code, time_elapsed, json.dumps(versions)))
        except Exception as e:
            print("ERROR: Unexpected error: Could not commit to database instance.")
            print(e)

    def record_source(self, base_id, source_id, user_id, stage, versions):
        try:
            with self.conn.connect() as cur:
                cur.execute("INSERT INTO source_label (base_id, source_id, user_id, stage, current_versions) VALUES (%s, %s, %s, %s, %s)", (base_id, source_id, user_id, stage, json.dumps(versions)))

        except Exception as e:
            print("ERROR: Unexpected error: Could not commit to database instance.")
            print(e)