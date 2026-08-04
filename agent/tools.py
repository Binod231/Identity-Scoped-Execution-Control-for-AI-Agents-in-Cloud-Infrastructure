"""
Agent Tool Definitions.

Defines the tools available to the simulated AI agent, matching the
format used by Claude's tool-use API. Each tool represents a category
of cloud infrastructure operations.
"""

TOOL_DEFINITIONS = [
    {
        "name": "aws_s3_operation",
        "description": "Perform operations on Amazon S3: create/delete buckets, upload/download objects, manage policies.",
        "actions": [
            "s3:CreateBucket", "s3:DeleteBucket", "s3:PutObject", "s3:GetObject",
            "s3:DeleteObject", "s3:ListBuckets", "s3:ListObjects",
            "s3:PutBucketPolicy", "s3:GetBucketPolicy",
        ],
    },
    {
        "name": "aws_ec2_operation",
        "description": "Manage Amazon EC2 instances, security groups, subnets, and VPCs.",
        "actions": [
            "ec2:RunInstances", "ec2:TerminateInstances", "ec2:StopInstances",
            "ec2:StartInstances", "ec2:DescribeInstances",
            "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup",
            "ec2:AuthorizeSecurityGroupIngress", "ec2:CreateSubnet",
            "ec2:DescribeSubnets", "ec2:DescribeVpcs",
            "ec2:CreateVpc", "ec2:DeleteVpc",
        ],
    },
    {
        "name": "aws_iam_operation",
        "description": "Manage AWS IAM: create/delete roles, policies, users, and policy attachments.",
        "actions": [
            "iam:CreateRole", "iam:DeleteRole", "iam:CreatePolicy",
            "iam:DeletePolicy", "iam:AttachRolePolicy", "iam:DetachRolePolicy",
            "iam:CreateUser", "iam:DeleteUser", "iam:PutRolePolicy",
            "iam:GetRole", "iam:ListRoles", "iam:ListPolicies", "iam:GetPolicy",
        ],
    },
    {
        "name": "aws_rds_operation",
        "description": "Manage Amazon RDS database instances, snapshots, and configurations.",
        "actions": [
            "rds:CreateDBInstance", "rds:DeleteDBInstance", "rds:ModifyDBInstance",
            "rds:DescribeDBInstances", "rds:CreateDBSnapshot",
            "rds:DeleteDBSnapshot", "rds:RestoreDBInstanceFromDBSnapshot",
        ],
    },
    {
        "name": "aws_cloudwatch_operation",
        "description": "Manage CloudWatch alarms, metrics, log groups, and retention policies.",
        "actions": [
            "cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms",
            "cloudwatch:DescribeAlarms", "cloudwatch:GetMetricData",
            "logs:CreateLogGroup", "logs:DeleteLogGroup",
            "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy",
            "logs:DescribeLogGroups",
        ],
    },
    {
        "name": "aws_lambda_operation",
        "description": "Manage AWS Lambda functions: create, update, invoke, and delete.",
        "actions": [
            "lambda:CreateFunction", "lambda:DeleteFunction",
            "lambda:UpdateFunctionCode", "lambda:InvokeFunction",
            "lambda:GetFunction", "lambda:ListFunctions",
        ],
    },
    {
        "name": "terraform_operation",
        "description": "Execute Terraform commands: plan, apply, destroy infrastructure.",
        "actions": ["terraform:plan", "terraform:apply", "terraform:destroy"],
    },
    {
        "name": "github_actions_operation",
        "description": "Trigger and manage GitHub Actions workflows.",
        "actions": ["github:trigger_workflow", "github:list_runs", "github:cancel_run"],
    },
]


def get_tool_for_action(action: str) -> str | None:
    """Look up which tool an action belongs to."""
    for tool in TOOL_DEFINITIONS:
        if action in tool["actions"]:
            return tool["name"]
    return None
