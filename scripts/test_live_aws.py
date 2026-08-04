"""
Live Real-AWS Testing Script for ScopeGuard.

Executes real read & query operations against your live AWS account
(S3, RDS, EC2, CloudWatch) intercepted and authorized by ScopeGuard.
"""

import asyncio
import json
import logging
from httpx import ASGITransport, AsyncClient

from proxy.main import app, lifespan
from proxy.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scopeguard.live_aws_test")


async def run_live_aws_test():
    """Issue real AWS tool calls through ScopeGuard."""
    logger.info("Initializing ScopeGuard Proxy for Live AWS Testing...")
    logger.info("Region: %s | Use LocalStack: %s | Mode: %s",
                settings.aws_region, settings.use_localstack, settings.proxy_mode)

    test_calls = [
        {
            "agent_id": "live-aws-agent-01",
            "session_id": "live-session-s3",
            "declared_task": "List all S3 storage buckets in AWS account",
            "tool_name": "aws_s3_operation",
            "tool_action": "s3:ListBuckets",
            "tool_params": {},
        },
        {
            "agent_id": "live-aws-agent-01",
            "session_id": "live-session-rds",
            "declared_task": "Describe database instances status and health",
            "tool_name": "aws_rds_operation",
            "tool_action": "rds:DescribeDBInstances",
            "tool_params": {},
        },
        {
            "agent_id": "live-aws-agent-01",
            "session_id": "live-session-ec2",
            "declared_task": "Describe running EC2 instances status",
            "tool_name": "aws_ec2_operation",
            "tool_action": "ec2:DescribeInstances",
            "tool_params": {},
        },
        {
            "agent_id": "live-aws-agent-01",
            "session_id": "live-session-cloudwatch",
            "declared_task": "Describe CloudWatch alarms for infrastructure monitoring",
            "tool_name": "aws_cloudwatch_operation",
            "tool_action": "cloudwatch:DescribeAlarms",
            "tool_params": {},
        },
    ]

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            print("\n" + "=" * 70)
            print("         SCOPEGUARD LIVE AWS DATA EXECUTION RESULTS         ")
            print("=" * 70)

            for item in test_calls:
                print(f"\n[+] Executing Task: '{item['declared_task']}'")
                print(f"    Action: {item['tool_action']} ({item['tool_name']})")

                response = await client.post("/execute-tool", json=item)
                if response.status_code == 200:
                    data = response.json()
                    print(f"    Scoping Decision: {data['decision']}")
                    print(f"    Audit Track ID:  {data['audit_id']}")
                    print(f"    Proxy Overhead:  {data['latency_ms']} ms")

                    if data['decision'] == 'ALLOWED':
                        result_str = data.get('result', '')
                        if result_str:
                            try:
                                parsed = json.loads(result_str)
                                print(f"    Real AWS Response Data:")
                                print(json.dumps(parsed, indent=6)[:500] + ("..." if len(str(parsed)) > 500 else ""))
                            except Exception:
                                print(f"    Raw AWS Result: {result_str[:200]}")
                    else:
                        print(f"    Blocked Reason: {data.get('error')}")
                else:
                    print(f"    HTTP Error: {response.status_code}")

            print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(run_live_aws_test())
