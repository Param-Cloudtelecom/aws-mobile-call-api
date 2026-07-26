# aws-mobile-call-api

![License](https://img.shields.io/github/license/Param-Cloudtelecom/aws-mobile-call-api) ![Top Language](https://img.shields.io/github/languages/top/Param-Cloudtelecom/aws-mobile-call-api) ![Last Commit](https://img.shields.io/github/last-commit/Param-Cloudtelecom/aws-mobile-call-api)


A serverless AWS backend (API Gateway + Lambda + DynamoDB) for a mobile
Cloud PBX app's two core features: **click-to-call** and **call history**.
This is the layer between a mobile app and the telecom stack itself — it
never talks to FreeSWITCH directly, it forwards over a VPC link to the
automation API from [`freeswitch-cloud-pbx`](https://github.com/Param-Cloudtelecom/freeswitch-cloud-pbx).

## Architecture

```
 Mobile App (iOS/Android)
        │  HTTPS + Cognito JWT
        ▼
 API Gateway (Cognito authorizer)
        │
        ├── POST /calls          ──► click_to_call.py ──► VPC link ──► FreeSWITCH originate API
        │
        └── GET /calls/{tenant}  ──► get_call_history.py ──► DynamoDB (CallHistoryTable)
```

## Why DynamoDB for call history, not a direct query to Postgres

The PBX's Postgres `cdr` table (see `freeswitch-cloud-pbx/sql/schema.sql`)
is the source of truth, but a mobile app's read path shouldn't add load to
production PBX infrastructure or share its network boundary. A small sync
job (not included here — typically a scheduled Lambda or a Postgres
logical replication consumer) mirrors recent CDRs into DynamoDB, and the
mobile API only ever reads from there.

## Security model

- Every request is authenticated via a **Cognito User Pool** JWT.
- `tenant_id` is read from the **verified token claim**
  (`custom:tenant_id`), never trusted from the request body or URL path —
  `get_call_history.py` explicitly checks the path parameter against the
  token claim before querying, so one tenant's mobile users can never read
  another tenant's call history even if they guess/forge a URL.
- Lambda reaches the PBX automation API over a **VPC link** with a locked
  -down security group (`FunctionSecurityGroup`, outbound 5000/tcp only) —
  the function has no public internet route to the PBX network.

## Files

- [`template.yaml`](template.yaml) — AWS SAM template: API Gateway with a
  Cognito authorizer, two Lambda functions, the DynamoDB table, and the VPC
  networking needed for Lambda to reach the PBX automation API privately.
- [`src/click_to_call.py`](src/click_to_call.py) — validates the request,
  forwards it to `POST /calls` on the FreeSWITCH automation API.
- [`src/get_call_history.py`](src/get_call_history.py) — tenant-scoped
  DynamoDB query for recent call history.

## Deploying

```bash
sam build
sam deploy --guided \
  --parameter-overrides \
    FreeswitchApiBase=http://10.0.1.50:5000 \
    CognitoUserPoolArn=arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_XXXXXXX \
    VpcId=vpc-xxxxxxxx \
    PrivateSubnetIds=subnet-aaaa,subnet-bbbb
```

## What I'd add for production

- API Gateway request throttling/usage plans per tenant tier
- A dead-letter queue on `click_to_call.py` for failed originate attempts,
  so a transient PBX-side issue doesn't just silently drop a user's call
  request
- X-Ray tracing across the API Gateway → Lambda → VPC link hop, since that's
  exactly the kind of multi-hop latency that's hard to diagnose without it
