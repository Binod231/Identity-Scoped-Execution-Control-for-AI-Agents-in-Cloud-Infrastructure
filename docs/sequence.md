# ScopeGuard — Request Sequence Diagram

The following sequence diagram details the complete interception, classification, policy evaluation, execution, and audit logging flow for every tool call handled by ScopeGuard.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Agent as AI Agent (Claude/Bedrock)
    participant Proxy as ScopeGuard Proxy (/execute-tool)
    participant Tagger as Identity Tagger
    participant Classifier as Task-to-Scope Classifier
    participant Policy as Policy Engine
    participant Executor as Backend Executor (AWS/LocalStack)
    participant Audit as SQLite Audit Log

    User->>Agent: "Deploy an EC2 instance in us-east-1"
    Agent->>Proxy: POST /execute-tool (agent_id, session_id, declared_task, tool_action)
    
    Proxy->>Tagger: extract_identity() & sanitize_params()
    Tagger-->>Proxy: Identity metadata (uuid, secrets redacted)
    
    Proxy->>Classifier: classify(declared_task)
    Classifier-->>Proxy: ScopeResult (allowed_actions, risk_level, confidence)
    
    Proxy->>Policy: evaluate(request, scope)
    
    alt Action is ALLOWED
        Policy-->>Proxy: ScopingDecision.ALLOWED
        Proxy->>Executor: execute(tool_name, tool_action, params)
        Executor-->>Proxy: Execution Result
    else Action is BLOCKED
        Policy-->>Proxy: ScopingDecision.BLOCKED
        Proxy-->>Proxy: Set Execution Error ("BLOCKED: off-scope")
    end

    Proxy->>Audit: log(AuditEntry)
    Audit-->>Proxy: Saved

    Proxy-->>Agent: ToolCallResponse (decision, result/error, latency_ms)
```
