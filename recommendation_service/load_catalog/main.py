#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Image Similarity App - Batch Load
"""

#Code management
from configparser import ConfigParser
import logging
#Other imports
import base64
import re
import typing
import time
#Flask imports
from flask_cors import CORS
from flask import Flask, request
# DataManagement
import sqlalchemy
#Google Cloud imports
from google.cloud import storage
from google.cloud import aiplatform
from google.protobuf import struct_pb2

#Init logging
logging.basicConfig(level=logging.INFO)

#Init flask
app = Flask(__name__)
CORS(app)
#

#Load variables
variables = ConfigParser()
variables.read("variables.ini")

# Read variables
project = variables.get("CORE","PROJECT")
location = variables.get("CORE","LOCATION")
catalog_repo = variables.get("CORE","CATALOG_REPO")
location = variables.get("CORE","LOCATION")
#seconds_per_job = variables.get("CORE","SECONDS_PER_JOB")
seconds_per_job=2
blob_uri_list = []

def generate_and_store_image_embedding(project, location, file_uri):
  """
  Retrieves the image embedding vector for a specified image file in GCS, using Vertex AI multi-model API and storing the result in a database

  :param str project: String representing the Google Cloud project for AI Platform access
  :param list location: String specifying the AI Platform location for the prediction model
  :param list file_uri: String containing the Google Cloud Storage URI of the image file
  :return json image_name: JSON object containing the image name that was stored in the database
  """
  # Read the image from the bucket in binary format
  image_bytes, image_name = _get_gcs_file_bytes (file_uri)
  # Encode the image in string format
  encodedString = _encode_image_to_base64 (image_bytes)

  api_regional_endpoint = f"{location}-aiplatform.googleapis.com"
  client_options = {"api_endpoint": api_regional_endpoint}
  client = aiplatform.gapic.PredictionServiceClient(client_options=client_options)

  endpoint = f"projects/{project}/locations/{location}/publishers/google/models/multimodalembedding@001"
  instance = struct_pb2.Struct()
  image_struct = instance.fields["image"].struct_value
  image_struct.fields["bytesBase64Encoded"].string_value = encodedString
  instances = [instance]
  response = client.predict(endpoint=endpoint, instances=instances)
  
  image_embedding: typing.Sequence[float]
  image_emb_value = response.predictions[0]['imageEmbedding']
  image_embedding = [v for v in image_emb_value]
  logging.info(f"Image Embedding: {image_embedding}")
  time.sleep(seconds_per_job)
  result=_load_embedding(image_name,image_embedding)

  if result is None:
    logging.info("There was an error while loading the embedding to the database")
    return 0
  else:
    logging.info("The embedding image has been loadaed in the database")
    return {"ImageName": image_name}

def _load_embedding(image_name, image_embedding):
  """
  Inserts an image embedding into a PostgreSQL database table and returns the IDs of matching entries based on the image name

  :param str image_name: Name of the image to insert in the database
  :param list image_embedding: Embedding representation of an image
  :return list image_id: IDs from the embedding image inserted in the database
  """
  pool = sqlalchemy.create_engine(
    # Equivalent URL:
    # postgresql+pg8000://<db_user>:<db_pass>@<INSTANCE_HOST>:<db_port>/<db_name>
    sqlalchemy.engine.url.URL.create(
            drivername="postgresql+pg8000",
            username="image_store",
            password="Image_001",
            host="127.0.0.1",
            port="5432",
            database="image_store",
    ),
  )

  insert_stm=_gen_insert_stm(image_name,image_embedding)
  insert_op = sqlalchemy.text(insert_stm)
#  print(insert_op)
  with pool.connect() as db_conn:

    # insert Load Data into database
    db_conn.execute(insert_op)
    db_conn.commit()

    # query database
    select_stm = "SELECT ID from catalog where PATH like '%" + image_name + "';"
    select_op = sqlalchemy.text(select_stm)
    result = db_conn.execute(select_op).fetchall()
    image_id = [ e[0] for e in result ]
    print(image_id)
#    connector.close()

  return image_id

def _gen_insert_stm (image_name, image_embedding):
  """
  Formulates an SQL INSERT statement for storing an image name and its embedding into the image_lookup table

  :param str image_name: Name of the image to insert in the database
  :param list image_embedding: Embedding representation of an image
  :return str insert_stm: SQL INSERT statement
  """
  str_image_embedding = str(image_embedding).replace("['","")
  insert_stm = "INSERT INTO catalog (PATH, EMBEDDING) VALUES ('" + image_name + "',array" + str_image_embedding + ");"
  return insert_stm

def _get_gcs_file_bytes(file_uri):
  """
  Retrieves the raw bytes and filename of an image stored in GCS based on its URI

  :param str file_uri: String containing the GCS URI of the image
  :return byte image_byte: Byte string containing the raw data of the downloaded image file
  :return str image_name: Filename of the downloaded image extracted from the URI
  """
  storage_client = storage.Client()
  bucket_name = file_uri.split("/")[2]
  image_name = file_uri.split("/")[3] 
  bucket = storage_client.bucket(bucket_name)
  blob = bucket.blob(image_name)

  image_bytes = blob.open("rb").read()
  return image_bytes, image_name

def _list_gcs_bucket_objects(bucket_name):
  """
  Retrieves a list of GCS URIs for all files (excluding directories) within a specified bucket

  :param str bucket_name: Name of the GCS Bucket
  :return list blob_uri_list: List of strings containing the GCS URIs for each file within the specified bucket
  """
  client = storage.Client()
  bucket = client.get_bucket(bucket_name)

  # List all the blobs in the specified folder
  blobs = bucket.list_blobs(delimiter=None)

  # Iterate through each blob and read its content
  for blob in blobs:
    if not blob.name.endswith("/"):  # Ignore directories
      image_name = blob.name
      blob_uri = "gs://" + bucket_name + "/" + image_name
      blob_uri_list.append(blob_uri)
  return blob_uri_list

def _encode_image_to_base64(image_bytes):
  """
  Converts raw image byte data into a Base64-encoded string

  :param byte image_byte: Byte string containing raw image data
  :return str encodedString: Encoded representation of the raw image data
  """
  encodedString = base64.b64encode(image_bytes).decode("utf-8") 
  return encodedString

if __name__ == '__main__':
  image_uri_list = _list_gcs_bucket_objects(catalog_repo)
  image_uri_list_filtered = image_uri_list[:300]
  for image in image_uri_list_filtered:
    generate_and_store_image_embedding(project, location, image)
