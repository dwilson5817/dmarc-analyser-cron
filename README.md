![DMARC Analyser logo](https://gitlab.dylanw.dev/uploads/-/system/group/avatar/14/dmarc-analyser-256px.png?width=96)

# DMARC Analyser Cron

[![Pipeline status](https://gitlab.dylanw.dev/dmarc-analyser/cron/badges/main/pipeline.svg)](https://gitlab.dylanw.dev/dmarc-analyser/cron/-/commits/main)

DMARC Analyser is an AWS Lambda-based DMARC report ingestion pipeline.  This repository contains two Lambda functions
responsible for ingesting DMARC reports into the pipeline.

- **email_scrape_cron** — runs on a schedule via EventBridge, connects to configured IMAP mailboxes, and uploads any
  DMARC report attachments to S3.  Mailbox credentials are retrieved from HashiCorp Vault using AWS IAM authentication.
- **s3_put_handler** — triggered by S3 object creation events, parses the DMARC XML reports and stores the results in
  DynamoDB.

## Development

### Email Scrape Cron

The following environment variables are required:

| Variable                    | Description                                          |
|-----------------------------|------------------------------------------------------|
| `S3_BUCKET`                 | The name of the S3 bucket to upload reports to       |
| `VAULT_ROLE`                | The Vault role to assume for credential retrieval    |
| `VAULT_ENGINE_MOUNT_POINT`  | The Vault secrets engine mount point (default: `secret`) |

Install the dependencies:

```bash
pip install -r email_scrape_cron/requirements.txt
```

### S3 Put Handler

The following environment variables are required:

| Variable         | Description                      |
|------------------|----------------------------------|
| `DYNAMODB_TABLE` | The name of the DynamoDB table   |

Install the dependencies:

```bash
pip install -r s3_put_handler/requirements.txt
```

## Deployment

This project uses the `python-lambda-build` and `python-lambda-upload` CI/CD components from
[cdk-deployment-base](https://gitlab.dylanw.dev/infrastructure/cdk-deployment-base) to build and upload the Lambda
function artifacts.  On the `main` branch, a deployment of the
[dmarc-analyser/cdk](https://gitlab.dylanw.dev/dmarc-analyser/cdk) project is triggered to apply any infrastructure
changes.

## License

This application is licensed under the GNU General Public License v3.0 or later.

```
DMARC Analyser - A Lambda-based DMARC report ingestion pipeline.
Copyright (C) 2026  Dylan Wilson

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```
