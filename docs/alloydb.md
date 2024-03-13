# Setup and configure AlloyDB
## Before you begin

1. Make sure you have a Google Cloud project and billing is enabled.

2. Set your PROJECT_ID environment variable:
```
export PROJECT_ID=<YOUR_PROJECT_ID>
```

3. [Install](https://cloud.google.com/sdk/docs/install) the gcloud CLI.

4. Set gcloud project:
```
gcloud config set project $PROJECT_ID
```
5. Enable APIs:
```
gcloud services enable alloydb.googleapis.com \
                       compute.googleapis.com \
                       cloudresourcemanager.googleapis.com \
                       servicenetworking.googleapis.com \
                       vpcaccess.googleapis.com \
                       aiplatform.googleapis.com
```

6. Install [python](https://cloud.google.com/python/docs/setup#installing_python) and set up a python virtual environment.

7. Make sure you have python version 3.11+ installed.

```
python -V
Download and install postgres-client cli (psql).
```

## Enable private services access
In this step, we will enable Private Services Access so that AlloyDB is able to connect to your VPC. You should only need to do this once per VPC (per project).

1. Set environment variables:
```
export RANGE_NAME=my-allocated-range-default
export DESCRIPTION="peering range for alloydb-service"
```

2. Create an allocated IP address range:
```
gcloud compute addresses create $RANGE_NAME \
    --global \
    --purpose=VPC_PEERING \
    --prefix-length=16 \
    --description="$DESCRIPTION" \
    --network=default
```

3. Create a private connection:
```
gcloud services vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --ranges="$RANGE_NAME" \
    --network=default
```

## Create a AlloyDB cluster
1. Set environment variables. For security reasons, use a different password for $DB_PASS and note it for future use:
```
export CLUSTER=my-alloydb-cluster
export DB_PASS=my-alloydb-pass
export INSTANCE=my-alloydb-instance
export REGION=us-central1
```

2. Create an AlloyDB cluster:
```
gcloud alloydb clusters create $CLUSTER \
    --password=$DB_PASS\
    --network=default \
    --region=$REGION \
    --project=$PROJECT_ID
```

3. Create a primary instance:
```
gcloud alloydb instances create $INSTANCE \
    --instance-type=PRIMARY \
    --cpu-count=8 \
    --region=$REGION \
    --cluster=$CLUSTER \
    --project=$PROJECT_ID \
    --ssl-mode=ALLOW_UNENCRYPTED_AND_ENCRYPTED
```

4. Get AlloyDB IP address:
```
export ALLOYDB_IP=$(gcloud alloydb instances describe $INSTANCE \
    --cluster=$CLUSTER \
    --region=$REGION \
    --format 'value(ipAddress)')
```
5. Note the AlloyDB IP address for later use:
```
echo $ALLOYDB_IP
```

### Set up connection to AlloyDB
AlloyDB supports network connectivity through private, internal IP addresses only. For this section, we will create a Google Cloud Engine VM in the same VPC as the AlloyDB cluster. We can use this VM to connect to our AlloyDB cluster using Private IP.

1. Set environment variables:
```
export ZONE=us-central1-a
export PROJECT_NUM=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
export VM_INSTANCE=alloydb-proxy-vm
```

2. Create a Compute Engine VM:
```
gcloud compute instances create $VM_INSTANCE \
    --project=$PROJECT_ID \
    --zone=$ZONE \
    --machine-type=e2-medium \
    --network-interface=network-tier=PREMIUM,stack-type=IPV4_ONLY,subnet=default \
    --maintenance-policy=MIGRATE \
    --provisioning-model=STANDARD \
    --service-account=$PROJECT_NUM-compute@developer.gserviceaccount.com \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --create-disk=auto-delete=yes,boot=yes,device-name=$VM_INSTANCE,image-family=ubuntu-2004-lts,image-project=ubuntu-os-cloud,mode=rw,size=10,type=projects/$PROJECT_ID/zones/$ZONE/diskTypes/pd-balanced \
    --no-shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring \
    --labels=goog-ec-src=vm_add-gcloud \
    --reservation-affinity=any
```

3. Create an SSH tunnel through your GCE VM using port forwarding. This will listen to 127.0.0.1:5432 and forward through the GCE VM to your AlloyDB instance:
```
gcloud compute ssh --project=$PROJECT_ID --zone=$ZONE $VM_INSTANCE \
                   -- -NL 5432:$ALLOYDB_IP:5432
```
You will need to allow this command to run while you are connecting to AlloyDB. You may wish to open a new terminal to connect with.

4. Verify you can connect to your instance with the psql tool. Enter password for AlloyDB ($DB_PASS environment variable set above) when prompted:
```
psql -h 127.0.0.1 -U postgres
```

## Initialize data in AlloyDB

1. While connected using psql, create a database and switch to it:
```
CREATE DATABASE assistantdemo;
\c assistantdemo
```

2. Install pgvector extension in the database:
```
CREATE EXTENSION vector;
```

3. Exit from psql:
```
exit
```

4. Change into the retrieval service directory:
```
cd genai-databases-retrieval-app/retrieval_service
```

5. Install requirements:
```
pip install -r requirements.txt
```

6. Make a copy of example-config.yml and name it config.yml.
```
cp example-config.yml config.yml
```

7. Update config.yml with your database information. Keep using 127.0.0.1 as the datastore host IP address for port forwarding.
```
host: 0.0.0.0
datastore:
  # Example for postgres.py provider
  kind: "postgres"
  host: 127.0.0.1
  port: 5432
  # Update this with the database name
  database: "assistantdemo"
  # Update with database user, the default is `postgres`
  user: "postgres"
  # Update with database user password
  password: "my-alloydb-pass"
```

8. Populate data into database:
```
python run_database_init.py
```

## Clean up resources
Clean up after completing the demo.

1. Set environment variables:
```
export VM_INSTANCE=alloydb-proxy-vm
export CLUSTER=my-alloydb-cluster
export REGION=us-central1
export RANGE_NAME=my-allocated-range-default
```

2. Delete Compute Engine VM:
```
gcloud compute instances delete $VM_INSTANCE
```

3. Delete AlloyDB cluster that contains instances:
```
gcloud alloydb clusters delete $CLUSTER \
    --force \
    --region=$REGION \
    --project=$PROJECT_ID
```

4. Delete an allocated IP address range:
```
gcloud compute addresses delete $RANGE_NAME \
    --global
```
