import json, logging, os, requests, time
import pandas as pd
from datetime import datetime, timedelta
from airflow.sdk import dag, task
from airflow.providers.mysql.hooks.mysql import MySqlHook

api_url = 'https://api.biodiversitydata.nl/v2'

task_logger = logging.getLogger('airflow.task')
default_args = {
    'owner': 'Mike',
    'retries': 5,
    'retry_delay': timedelta(seconds=30)
}


@dag(
    dag_id='ingest_nba_data_v26',
    default_args=default_args,
    schedule='@daily',
    start_date=datetime(2025,7,18),
    catchup=False
)
def ingest_nba_data():
    @task
    def extract() -> str:
        task_logger.info('Extracting Data from Netherlands Biodata API')

        base_request_body = {
            'conditions': [
            {
                'field': 'gatheringEvent.locality',
                'operator': 'NOT_EQUALS',
                'value': None
            },
            {
                'field': 'gatheringEvent.siteCoordinates.longitudeDecimal',
                'operator': 'NOT_EQUALS',
                'value': 0
            },
            {
                'field': 'gatheringEvent.siteCoordinates.latitudeDecimal',
                'operator': 'NOT_EQUALS',
                'value': 0
            },
            {
                'field': 'gatheringEvent.dateTimeBegin',
                'operator': 'NOT_EQUALS',
                'value': None
            },
            {
                'field': 'gatheringEvent.dateTimeEnd',
                'operator': 'NOT_EQUALS',
                'value': None
            },
            {
                'field': 'identifications.dateIdentified',
                'operator': 'NOT_EQUALS',
                'value': None
            },
            {
                'field': 'identifications.defaultClassification.kingdom',
                'operator': 'EQUALS_IC',
                'value': 'Plantae'
            },
            {
                'field': 'associatedMultiMediaUris.format',
                'operator': 'NOT_EQUALS',
                'value': None
            }
        ],
            'logicalOperator': 'AND',
            'size': 1000,
            'from': 0
        }

        current_from = 0
        page_size = 1000
        total_size = 50000
        page_files = []

        os.makedirs('temp', exist_ok=True)

        while True:
            request_body = base_request_body.copy()
            request_body['from'] = current_from

            task_logger.info(f'Requesting Records from {current_from} to {current_from + page_size - 1}')

            try:
                response = requests.post(f'{api_url}/specimen/query', json=request_body, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if total_size is None:
                    total_size = data.get('totalSize', 0)
                    task_logger.info(f'Total Records Available: {total_size}')

                result_set = data.get('resultSet', [])

                if not result_set:
                    task_logger.info('No more Records found, reached end')
                    break

                page_num = current_from // page_size
                page_file_path = f'temp/raw_biodata_page_{page_num:04d}.json'
                with open(page_file_path, 'w') as f:
                    json.dump(result_set, f)

                page_files.append(page_file_path)
                task_logger.info(f'Saved {len(result_set)} Records to {page_file_path}. Total Pages so far: {len(page_files)}')

                if current_from + page_size >= total_size:
                    task_logger.info(f'Reached end of Data. Retrieved {len(page_files)} Pages')
                    break

                current_from += page_size

            except requests.exceptions.Timeout:
                task_logger.warning(f'Request Timeout for Page {current_from}, retrying shortly')
                time.sleep(5)
                continue
            except requests.exceptions.RequestException as e:
                if hasattr(e, 'response') and e.response is not None:
                    if e.response.status_code == 429:
                        task_logger.warning(f'Rate Limit Exceeded, retrying after 30 seconds')
                        time.sleep(30)
                        continue
                    elif e.response.status_code >= 500:
                        task_logger.warning(f'Server Error {e.response.status_code}, retrying after 10 seconds')
                        time.sleep(10)
                        continue
                task_logger.error(f'Error Requesting Data from NBA: {str(e)}')
                raise
            except Exception as e:
                task_logger.error(f'Unexpected Error during Pagination: {str(e)}')
                raise
        
        manifest_path = 'temp/raw_biodata_manifest.json'
        manifest = {
            'total_size': total_size,
            'page_size': page_size,
            'total_pages': len(page_files),
            'page_files': page_files
        }

        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        task_logger.info(f'Successfully Extracted {total_size} Records across {len(page_files)} Pages')

        return manifest_path
    
    @task
    def transform(manifest_path: str) -> str:
        task_logger.info('Transforming the Extracted Data')

        def parse_date(date_str):
            if date_str and isinstance(date_str, str):
                try:
                    return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S%z').strftime('%Y-%m-%d')
                except ValueError:
                    return None
            return None

        with open(manifest_path) as f:
            manifest = json.load(f)

        page_files = manifest['page_files']
        total_pages = manifest['total_pages']
        task_logger.info(f'Processing {total_pages} Page Files')

        transformed_files = []

        for i, page_file in enumerate(page_files):
            task_logger.info(f'Transforming Page {i + 1}/{total_pages} from {page_file}')

            with open(page_file) as f:
                raw_page = json.load(f)
            
            page_records = []

            for record in raw_page:
                item = record['item']
                gathering = item.get('gatheringEvent', {})
                identification = item.get('identifications', [{}])[0]
                sci_name = identification.get('scientificName', {})
                classification = identification.get('defaultClassification', {})
                media = item.get('associatedMultiMediaUris', [{}])[0]

                date_identified = parse_date(identification.get('dateIdentified'))
                date_time_begin = parse_date(gathering.get('dateTimeBegin'))
                date_time_end = parse_date(gathering.get('dateTimeEnd'))

                page_records.append({
                    'id': item.get('id'),
                    'unit_id': item.get('unitID'),
                    'unit_guid': item.get('unitGUID'),
                    'source_institution_id': item.get('sourceInstitutionID'),
                    'source_id': item.get('sourceID'),
                    'record_basis': item.get('recordBasis'),
                    'collection_type': item.get('collectionType'),
                    'object_public': item.get('objectPublic'),
                    'world_region': gathering.get('worldRegion'),
                    'continent': gathering.get('continent'),
                    'country': gathering.get('country'),
                    'province_state': gathering.get('provinceState'),
                    'locality': gathering.get('locality'),
                    'locality_text': gathering.get('localityText'),
                    'altitude': gathering.get('altitude'),
                    'altitude_unit': gathering.get('altitudeUnitOfMeasurement'),
                    'date_time_begin': date_time_begin,
                    'date_time_end': date_time_end,
                    'biotope_text': gathering.get('biotopeText'),
                    'gathering_person_full_name': gathering.get('gatheringPersons', [{}])[0].get('fullName'),
                    'longitude': gathering.get('siteCoordinates', [{}])[0].get('longitudeDecimal'),
                    'latitude': gathering.get('siteCoordinates', [{}])[0].get('latitudeDecimal'),
                    'taxon_rank': identification.get('taxonRank'),
                    'full_scientific_name': sci_name.get('fullScientificName'),
                    'genus_or_monomial': sci_name.get('genusOrMonomial'),
                    'specific_epithet': sci_name.get('specificEpithet'),
                    'authorship': sci_name.get('authorshipVerbatim'),
                    'scientific_name_group': sci_name.get('scientificNameGroup'),
                    'date_identified': date_identified,
                    'kingdom': classification.get('kingdom'),
                    'order_name': classification.get('order'),
                    'family': classification.get('family'),
                    'identifier_agent': identification.get('identifiers', [{}])[0].get('agentText'),
                    'image_url': media.get('accessUri'),
                    'image_format': media.get('format'),
                    'image_variant': media.get('variant'),
                    'notes': item.get('notes')
                })

            page_num = i
            transformed_file = f'temp/clean_biodata_page_{page_num:04d}.json'
            
            df = pd.DataFrame(page_records)
            df.to_json(transformed_file, orient='records', indent=2)

            transformed_files.append(transformed_file)
            task_logger.info(f'Transformed Page {i + 1}/{total_pages} to {transformed_file} ({len(page_records)} Records)')

        transformed_manifest = {
            'total_pages': len(transformed_files),
            'files': transformed_files,
            'original_manifest': manifest_path
        }
        manifest_path = 'temp/clean_biodata_manifest.json'

        with open(manifest_path, 'w') as f:
            json.dump(transformed_manifest, f, indent=2)

        task_logger.info(f'Successfully Transformed {len(transformed_files)} Files.')
        
        return manifest_path

    @task
    def load(manifest_path: str):
        task_logger.info('Loading Data into MySQL Database')

        def chunked(iterable, size):
                for i in range(0, len(iterable), size):
                    yield iterable[i:i + size]
        
        with open(manifest_path) as f:
            manifest = json.load(f)

        transformed_files = manifest['files']
        total_files = manifest['total_pages']
        
        mysql_hook = MySqlHook(mysql_conn_id='mysql_localhost')
        conn = mysql_hook.get_conn()
        cur = conn.cursor()

        try:
            create_biodata_table_query = """
            CREATE TABLE IF NOT EXISTS biodiversity_data (
                id VARCHAR(50),
                unit_id VARCHAR(50),
                unit_guid VARCHAR(250),
                source_institution_id VARCHAR(100),
                source_id VARCHAR(100),
                record_basis VARCHAR(100),
                collection_type VARCHAR(250),
                object_public BOOLEAN,
                notes VARCHAR(5000),
                world_region VARCHAR(50),
                continent VARCHAR(50),
                country VARCHAR(100),
                province_state VARCHAR(100),
                locality VARCHAR(1000),
                locality_text VARCHAR(2500),
                altitude VARCHAR(50),
                altitude_unit VARCHAR(10),
                date_time_begin DATETIME,
                date_time_end DATETIME,
                biotope_text VARCHAR(1000),
                gathering_person_full_name VARCHAR(500),
                longitude DOUBLE,
                latitude DOUBLE,
                taxon_rank VARCHAR(50),
                kingdom VARCHAR(50),
                order_name VARCHAR(50),
                family VARCHAR(50),
                full_scientific_name VARCHAR(500),
                genus_or_monomial VARCHAR(100),
                specific_epithet VARCHAR(100),
                authorship VARCHAR(250),
                scientific_name_group VARCHAR(100),
                date_identified DATETIME,
                identifier_agent VARCHAR(250),
                image_url VARCHAR(100),
                image_format VARCHAR(20),
                image_variant VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                INDEX idx_country (country),
                INDEX idx_genus_or_monomial (genus_or_monomial)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            cur.execute(create_biodata_table_query)
            conn.commit()
            task_logger.info('Table Created')
            
            insert_biodata_sql = """
            INSERT INTO biodiversity_data (
                id, unit_id, unit_guid, source_institution_id, source_id, record_basis,
                collection_type, object_public, notes, world_region, continent, country,
                province_state, locality, locality_text, altitude, altitude_unit, date_time_begin,
                date_time_end, biotope_text, gathering_person_full_name, longitude, latitude,
                taxon_rank, kingdom, order_name, family, full_scientific_name, genus_or_monomial,
                specific_epithet, authorship, scientific_name_group, date_identified,
                identifier_agent, image_url, image_format, image_variant
            ) VALUES (
                %(id)s, %(unit_id)s, %(unit_guid)s, %(source_institution_id)s, %(source_id)s, %(record_basis)s,
                %(collection_type)s, %(object_public)s, %(notes)s, %(world_region)s, %(continent)s,
                %(country)s, %(province_state)s, %(locality)s, %(locality_text)s, %(altitude)s,
                %(altitude_unit)s, %(date_time_begin)s, %(date_time_end)s, %(biotope_text)s,
                %(gathering_person_full_name)s, %(longitude)s, %(latitude)s, %(taxon_rank)s, %(kingdom)s,
                %(order_name)s, %(family)s, %(full_scientific_name)s, %(genus_or_monomial)s,
                %(specific_epithet)s, %(authorship)s, %(scientific_name_group)s, %(date_identified)s,
                %(identifier_agent)s, %(image_url)s, %(image_format)s, %(image_variant)s
            )
            ON DUPLICATE KEY UPDATE
                unit_guid = VALUES(unit_guid),
                source_institution_id = VALUES(source_institution_id),
                source_id = VALUES(source_id),
                record_basis = VALUES(record_basis),
                collection_type = VALUES(collection_type),
                object_public = VALUES(object_public),
                notes = VALUES(notes),
                locality_text = VALUES(locality_text),
                order_name = VALUES(order_name),
                family = VALUES(family),
                full_scientific_name = VALUES(full_scientific_name),
                genus_or_monomial = VALUES(genus_or_monomial),
                specific_epithet = VALUES(specific_epithet),
                authorship = VALUES(authorship),
                scientific_name_group = VALUES(scientific_name_group),
                date_identified = VALUES(date_identified),
                identifier_agent = VALUES(identifier_agent),
                image_url = VALUES(image_url),
                image_format = VALUES(image_format),
                image_variant = VALUES(image_variant),
                updated_at = CURRENT_TIMESTAMP
            """
            
            total_records_loaded = 0
            batch_size = 500

            for file_idx, transformed_file in enumerate(transformed_files):
                task_logger.info(f'Inserting Data from File {transformed_file} ({file_idx + 1}/{total_files})')

                with open(transformed_file) as f:
                    file_data = json.load(f)

                try:
                    for batch in chunked(file_data, batch_size):
                        cur.executemany(insert_biodata_sql, batch)
                        total_records_loaded += len(batch)
                        task_logger.info(f'Inserted Batch of {len(batch)} from File {file_idx + 1}')

                    conn.commit()
                    task_logger.info(f'Commited File {file_idx + 1}/{total_files}')

                except Exception as e:
                    conn.rollback()
                    task_logger.error(f'Error Inserting File {file_idx + 1}: {str(e)}')
                    raise

            task_logger.info(f'Successfully Loaded {total_records_loaded} Records from {total_files} Files into biodiversity_data Table')
        
        finally:
            cur.close()
            conn.close()

    load(transform(extract()))
    # Enable this to skip the extract task to more quickly debug the transform and load tasks
    # This only works of course if you've already ran the extract task once before.
    # load(transform('temp/raw_biodata_manifest.json'))

dag = ingest_nba_data()
