"""
get_call_history.py - Lambda handler behind API Gateway's GET /calls/{tenant_id}.

Reads from DynamoDB (a fast, app-facing mirror of the Postgres `cdr` table
from freeswitch-cloud-pbx) instead of querying the PBX database directly -
keeps the mobile app's read path decoupled from PBX database load.
"""
import json
import os
import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ["CALL_HISTORY_TABLE"]
dynamodb = boto3.resource("dynamodb")


def handler(event, context):
    path_tenant_id = event.get("pathParameters", {}).get("tenant_id")
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    token_tenant_id = claims.get("custom:tenant_id")

    # Defense in depth: even though API Gateway's authorizer already
    # validated the token, never trust a path parameter blindly - confirm
    # it matches the tenant on the caller's own token.
    if path_tenant_id != token_tenant_id:
        return _response(403, {"error": "tenant mismatch"})

    limit = int(event.get("queryStringParameters", {}).get("limit", 25))

    table = dynamodb.Table(TABLE_NAME)
    result = table.query(
        KeyConditionExpression=Key("tenant_id").eq(path_tenant_id),
        ScanIndexForward=False,  # most recent first
        Limit=limit,
    )

    return _response(200, result.get("Items", []))


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }
