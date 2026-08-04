"""
Unit tests for TaskToScopeClassifier.
"""

from proxy.classifier import TaskToScopeClassifier
from proxy.models import RiskLevel


def test_classifier_compute(classifier: TaskToScopeClassifier):
    scope = classifier.classify("Deploy an EC2 instance in us-east-1")
    assert "ec2:RunInstances" in scope.allowed_actions
    assert scope.confidence > 0.0
    assert scope.risk_level.value in ("MEDIUM", "HIGH")


def test_classifier_storage(classifier: TaskToScopeClassifier):
    scope = classifier.classify("Create S3 bucket for assets storage")
    assert "s3:CreateBucket" in scope.allowed_actions
    assert "s3:ListBuckets" in scope.allowed_actions  # implicit read grant


def test_classifier_empty_task(classifier: TaskToScopeClassifier):
    scope = classifier.classify("")
    assert len(scope.allowed_actions) == 0
    assert scope.confidence == 0.0


def test_classifier_unknown_task(classifier: TaskToScopeClassifier):
    scope = classifier.classify("Do some completely unrelated operation like baking a cake")
    assert len(scope.allowed_actions) == 0
    assert scope.confidence == 0.0
