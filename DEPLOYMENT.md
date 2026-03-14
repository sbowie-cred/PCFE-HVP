# spcs deployment guide

this guide walks through building and deploying the hvp dashboard to snowflake container service (spcs).

## prerequisites

- docker desktop or docker engine installed locally
- snowflake account with container service enabled
- `snow` cli (snowflake's native command line tool) or `snowsql`
- appropriate roles/permissions in snowflake for creating image repositories and services

## step 1: build the docker image locally

```bash
cd "C:\Users\sbowie\Documents\PCFE HVP"
docker build -t hvp-dashboard:1.0 .
```

verify the build succeeded:
```bash
docker images | grep hvp-dashboard
```

### test locally (optional)

to test before pushing:
```bash
docker run -p 8080:8080 hvp-dashboard:1.0
```

the app should be available at `http://localhost:8080` (note: snowflake auth won't work locally without credentials).

## step 2: get your snowflake registry hostname

in snowflake (sql):
```sql
show image repositories in schema <YOUR_DATABASE>.<YOUR_SCHEMA>;
```

this returns the registry hostname. it looks like:
```
<ACCOUNT_ID>.registry.<REGION>.snowflakecomputing.com
```

## step 3: authenticate docker to snowflake registry

```bash
docker login <REGISTRY_HOSTNAME> -u <SNOWFLAKE_USERNAME>
```

you'll be prompted for a password. use your snowflake password or a temporary session token.

## step 4: tag your image for the registry

```bash
docker tag hvp-dashboard:1.0 <REGISTRY_HOSTNAME>/<DATABASE>/<SCHEMA>/hvp-dashboard:1.0
```

example:
```bash
docker tag hvp-dashboard:1.0 myaccount.registry.us-east-2.snowflakecomputing.com/hvp_db/hvp_schema/hvp-dashboard:1.0
```

## step 5: push to snowflake registry

```bash
docker push <REGISTRY_HOSTNAME>/<DATABASE>/<SCHEMA>/hvp-dashboard:1.0
```

this may take 1-2 minutes depending on network speed.

verify:
```bash
show images in repository <DATABASE>.<SCHEMA>.hvp-dashboard;
```

## step 6: update spec.yml

edit `spec.yml` and replace `<REGISTRY_HOSTNAME>`, `<DATABASE>`, `<SCHEMA>`, `<IMAGE_REPOSITORY>`, `<TAG>` with your actual values:

```yaml
image: myaccount.registry.us-east-2.snowflakecomputing.com/hvp_db/hvp_schema/hvp-dashboard:1.0
```

## step 7: create and deploy the service

use snowsql or the python snowpark api:

### option a: snowsql

```sql
create service hvp_dashboard
	in compute pool <COMPUTE_POOL_NAME>
	from specification_file = '@~/spec.yml'
	auto_resume = true;
```

### option b: snow cli

```bash
snow spcs service create --name hvp_dashboard --pool <COMPUTE_POOL_NAME> --spec-path ./spec.yml
```

## step 8: monitor the service

check service status:
```sql
show services in compute pool <COMPUTE_POOL_NAME>;
select *
from table(result_scan(last_query_id()))
where name = 'hvp_dashboard';
```

view logs:
```sql
call system$get_service_logs('hvp_dashboard', 0, 'main');
```

get the public endpoint:
```sql
select *
from table(result_scan(last_query_id()))
where name = 'hvp_dashboard';
-- look for the "public_endpoint_url" column
```

## step 9: access the dashboard

once the service is running and healthy, visit:
```
https://<PUBLIC_ENDPOINT_URL>
```

the app should load with snowflake automatically providing credentials via spcs injection.

## troubleshooting

### service won't start

check logs:
```sql
call system$get_service_logs('hvp_dashboard', 0, 'main');
```

common issues:
- wrong warehouse name (ensure `FRA` exists and user has access)
- image not found in registry (verify push succeeded)
- insufficient compute pool resources

### app returns 500 errors

check for snowflake connection issues:
```sql
call system$get_service_logs('hvp_dashboard', 0, 'main');
```

verify:
- snowflake session can access `cashflow_engine.fra_pcfe.model_scenario` table
- user role has appropriate grants
- warehouse `FRA` has sufficient credits

### want to update the image

1. make code changes
2. rebuild: `docker build -t hvp-dashboard:2.0 .`
3. push: `docker tag ... && docker push ...`
4. update service:
   ```sql
   alter service hvp_dashboard set spec = $$
   spec:
     containers:
       - name: hvp-dashboard
         image: <NEW_IMAGE_WITH_NEW_TAG>
   $$;
   ```

## cleanup

to remove the service:
```sql
drop service hvp_dashboard;
```

to remove the image repository:
```sql
drop image repository hvp_db.hvp_schema.hvp-dashboard;
```

## references

- [snowflake container service docs](https://docs.snowflake.com/developer-guide/containerized-services)
- [snowflake registry docs](https://docs.snowflake.com/developer-guide/containerized-services/registry)
