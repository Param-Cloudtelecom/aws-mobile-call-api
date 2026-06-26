"""
click_to_call.py - Lambda handler behind API Gateway's POST /calls.

Authenticated mobile app users hit this through Cognito; the function
itself just validates input and forwards the request over a VPC link to
the FreeSWITCH originate API (see the freeswitch-cloud-pbx repo's
api/originate.py) running inside the VPC - the mobile app never talks to
the PBX network directly.
"""
import json
import os
import urllib.request
import urllib.error

FREESWITCH_API_BASE = os.environ["FREESWITCH_API_BASE"]


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid JSON body"})

    # Cognito authorizer puts verified claims here - use the tenant claim
    # from the token rather than trusting a tenant_id in the request body.
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    tenant_id = claims.get("custom:tenant_id")
    from_extension = body.get("from_extension")
    to_number = body.get("to_number")

    if not tenant_id:
        return _response(403, {"error": "no tenant claim on this user's token"})
    if not from_extension or not to_number:
        return _response(400, {"error": "from_extension and to_number are required"})

    payload = json.dumps({
        "tenant_id": tenant_id,
        "from_extension": from_extension,
        "to_number": to_number,
    }).encode()

    req = urllib.request.Request(
        f"{FREESWITCH_API_BASE}/calls",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return _response(resp.status, json.loads(resp.read()))
    except urllib.error.HTTPError as e:
        return _response(e.code, {"error": e.reason})
    except urllib.error.URLError:
        return _response(502, {"error": "could not reach call origination service"})


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
