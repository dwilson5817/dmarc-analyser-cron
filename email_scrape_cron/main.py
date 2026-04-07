import email
import gzip
import io
import os
import zipfile
from typing import cast
from imaplib import IMAP4_SSL

import boto3
import hvac
from botocore.exceptions import ClientError
from aws_lambda_powertools.utilities.typing import LambdaContext

s3_bucket = os.environ['S3_BUCKET']
vault_engine_mount_point = os.environ.get('VAULT_ENGINE_MOUNT_POINT', 'secret')
vault_role = os.environ['VAULT_ROLE']

s3 = boto3.client('s3')


def decompress(filename: str, data: bytes) -> tuple[str, bytes]:
    if filename.endswith('.xml.gz') or filename.endswith('.xml.gzip'):
        xml_name = filename.rsplit('.', 1)[0]
        return xml_name, gzip.decompress(data)
    if filename.endswith('.xml.zip') or filename.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml_name = next(n for n in zf.namelist() if n.endswith('.xml'))
            return xml_name, zf.read(xml_name)
    return filename, data


def upload_to_s3(account_name: str, key: str, data: bytes) -> bool:
    """Upload data to S3. Returns True if uploaded, False if already exists."""
    s3_key = f"{account_name}/{key}"
    try:
        s3.head_object(Bucket=s3_bucket, Key=s3_key)
        return False
    except ClientError as e:
        if e.response['Error']['Code'] != '404':
            raise
    s3.put_object(Bucket=s3_bucket, Key=s3_key, Body=data, ContentType='application/xml')
    return True


def process_account(account_name: str, credentials: dict) -> None:
    with IMAP4_SSL(host=credentials['mail_host'], port=int(credentials['mail_port'])) as M:
        M.login(credentials['mail_user'], credentials['mail_pass'])
        M.select()

        typ, data = M.search(None, 'ALL')
        for num in data[0].split():
            typ, data = M.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])

            if msg['To'] != credentials['aggregate_reports_addr']:
                continue

            results = []
            for part in msg.walk():
                if part.get_content_disposition() != 'attachment':
                    continue
                filename = part.get_filename()
                if not filename:
                    continue
                xml_name, xml_data = decompress(filename, cast(bytes, part.get_payload(decode=True)))
                uploaded = upload_to_s3(account_name, xml_name, xml_data)
                results.append(f"{xml_name} ({'uploaded' if uploaded else 'already exists'})")

            print(f"[{account_name}] {msg['Subject']}: {results or 'no attachments found'}")

        M.close()
        M.logout()


def handler(event: dict, context: LambdaContext):
    credentials = boto3.Session().get_credentials()
    vault = hvac.Client()
    vault.auth.aws.iam_login(
        access_key=credentials.access_key,
        secret_key=credentials.secret_key,
        session_token=credentials.token,
        role=vault_role
    )

    accounts = vault.secrets.kv.v2.list_secrets(path='accounts', mount_point=vault_engine_mount_point)
    for account_name in accounts['data']['keys']:
        if account_name.endswith('/'):
            continue
        secret = vault.secrets.kv.v2.read_secret_version(path=f'accounts/{account_name}', mount_point=vault_engine_mount_point)
        process_account(account_name, secret['data']['data'])
