import os
import xml.etree.ElementTree as ET
from urllib.parse import unquote_plus

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext

dynamodb_table = os.environ['DYNAMODB_TABLE']

s3 = boto3.client('s3')
table = boto3.resource('dynamodb').Table(dynamodb_table)


def parse_report(xml_data: bytes) -> tuple[dict, list[dict]]:
    root = ET.fromstring(xml_data)

    metadata = root.find('report_metadata')
    date_range = metadata.find('date_range')
    policy = root.find('policy_published')

    report_id = metadata.findtext('report_id')
    begin_date = int(date_range.findtext('begin'))
    domain = policy.findtext('domain')

    report_item = {
        'PK': f'DOMAIN#{domain}',
        'SK': f'REPORT#{begin_date}#{report_id}',
        'report_id': report_id,
        'org_name': metadata.findtext('org_name'),
        'org_email': metadata.findtext('email'),
        'begin_date': begin_date,
        'end_date': int(date_range.findtext('end')),
        'adkim': policy.findtext('adkim', default='r'),
        'aspf': policy.findtext('aspf', default='r'),
        'policy': policy.findtext('p'),
        'subdomain_policy': policy.findtext('sp'),
        'pct': int(policy.findtext('pct', default='100')),
    }

    record_items = []
    for record in root.findall('record'):
        row = record.find('row')
        policy_evaluated = row.find('policy_evaluated')
        identifiers = record.find('identifiers')
        auth_results_el = record.find('auth_results')

        source_ip = row.findtext('source_ip')

        auth_results = []
        for dkim in auth_results_el.findall('dkim'):
            auth_results.append({
                'type': 'dkim',
                'domain': dkim.findtext('domain'),
                'result': dkim.findtext('result'),
            })
        for spf in auth_results_el.findall('spf'):
            auth_results.append({
                'type': 'spf',
                'domain': spf.findtext('domain'),
                'result': spf.findtext('result'),
            })

        record_items.append({
            'PK': f'REPORT#{report_id}',
            'SK': f'RECORD#{source_ip}',
            'source_ip': source_ip,
            'count': int(row.findtext('count')),
            'disposition': policy_evaluated.findtext('disposition'),
            'dkim_aligned': policy_evaluated.findtext('dkim'),
            'spf_aligned': policy_evaluated.findtext('spf'),
            'header_from': identifiers.findtext('header_from'),
            'auth_results': auth_results,
        })

    return report_item, record_items


def handler(event: dict, context: LambdaContext):
    for s3_record in event['Records']:
        bucket = s3_record['s3']['bucket']['name']
        key = unquote_plus(s3_record['s3']['object']['key'])

        response = s3.get_object(Bucket=bucket, Key=key)
        xml_data = response['Body'].read()

        report_item, record_items = parse_report(xml_data)

        with table.batch_writer() as batch:
            batch.put_item(Item=report_item)
            for record_item in record_items:
                batch.put_item(Item=record_item)

        domain = report_item['PK'].removeprefix('DOMAIN#')
        table.update_item(
            Key={'PK': 'META', 'SK': 'DOMAINS'},
            UpdateExpression='ADD domains :domain',
            ExpressionAttributeValues={':domain': {domain}},
        )

        print(f"Stored report {report_item['report_id']} with {len(record_items)} records from s3://{bucket}/{key}")
