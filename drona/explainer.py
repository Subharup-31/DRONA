# drona/explainer.py
from __future__ import annotations
import os
import json
import socket
import urllib.request
from drona.schema import CausalEdge, IncidentMatch
from drona.identity import IdentityLayer


SYSTEM_PROMPT = (
    "You are a senior SRE analyzing a production incident. Respond in exactly "
    "3 sentences. Sentence 1: what happened and which service. Sentence 2: most "
    "likely root cause. Sentence 3: recommended immediate action. Be specific, "
    "technical, and concise. No preamble. No bullet points. Max 80 words."
)


def generate_explain(
    related: list[dict],
    chain: list[CausalEdge],
    similar: list[IncidentMatch],
    mode: str,
    identity: IdentityLayer,
) -> str:
    """Generate incident explanation. Uses template for fast mode, LLM for deep."""
    if mode != "deep":
        return _template(related, chain, similar, identity)

    backend = os.getenv("DRONA_LLM_BACKEND", "template")
    try:
        prompt = _build_prompt(related, chain, similar, identity)
        if backend == "bedrock":
            return _bedrock(prompt)
        if backend == "openrouter":
            return _openrouter(prompt)
        return _template(related, chain, similar, identity)
    except Exception:
        return _template(related, chain, similar, identity) + " [deep mode unavailable]"


def _template(
    related: list[dict],
    chain: list[CausalEdge],
    similar: list[IncidentMatch],
    identity: IdentityLayer,
) -> str:
    """Pure string template backend — zero cost, zero network."""
    # Part 1 — what happened
    deploy_event = next(
        (e for e in related if e.get("kind") == "deploy"), None
    )
    if deploy_event:
        svc = deploy_event.get("service") or deploy_event.get("svc", "unknown")
        try:
            svc_name = identity.current_name(identity.resolve(svc))
        except Exception:
            svc_name = svc
        version = deploy_event.get("version", "unknown")
        part1 = (
            f"A deployment of {svc_name} ({version}) preceded this incident."
        )
    else:
        part1 = "No recent deployment identified in the observation window."

    # Part 2 — likely cause
    if chain:
        c = chain[0]
        try:
            cause = identity.current_name(c.cause_id)
        except Exception:
            cause = c.cause_id
        try:
            effect = identity.current_name(c.effect_id)
        except Exception:
            effect = c.effect_id
        part2 = f"Likely causal path: {cause} → {effect} (confidence {c.confidence:.0%})."
    else:
        part2 = "No clear causal path identified."

    # Part 3 — recommendation
    if similar:
        m = similar[0]
        part3 = (
            f"Closest match: {m.past_incident_id} "
            f"({m.similarity:.0%} similarity); {m.rationale}."
        )
    else:
        part3 = "No historical match found — treat as novel incident."

    return " ".join([part1, part2, part3])


def _build_prompt(
    related: list[dict],
    chain: list[CausalEdge],
    similar: list[IncidentMatch],
    identity: IdentityLayer,
) -> str:
    """Build compact LLM prompt from context data."""
    lines: list[str] = []

    # Unique services
    svcs: set[str] = set()
    for e in related:
        svc = e.get("service") or e.get("svc")
        if svc:
            try:
                svcs.add(identity.current_name(identity.resolve(svc)))
            except Exception:
                svcs.add(svc)
    if svcs:
        lines.append(f"Services involved: {', '.join(sorted(svcs))}")

    # Deploy
    deploy = next((e for e in related if e.get("kind") == "deploy"), None)
    if deploy:
        svc = deploy.get("service") or deploy.get("svc", "unknown")
        try:
            svc_name = identity.current_name(identity.resolve(svc))
        except Exception:
            svc_name = svc
        lines.append(f"Deploy: {svc_name} → {deploy.get('version', '?')}")

    # Metric anomalies
    for e in related:
        if e.get("kind") == "metric" and e.get("_provenance", {}).get("is_anomaly"):
            svc = e.get("service") or e.get("svc", "?")
            lines.append(
                f"Metric spike: {e.get('name', '?')} = {e.get('value', '?')} on {svc}"
            )
            break

    # Error logs
    for e in related:
        if e.get("kind") == "log" and e.get("level") == "error":
            lines.append(f"Error: {str(e.get('msg', ''))[:100]}")
            break

    # Causal edges
    if chain:
        c = chain[0]
        try:
            cause = identity.current_name(c.cause_id)
        except Exception:
            cause = c.cause_id
        try:
            effect = identity.current_name(c.effect_id)
        except Exception:
            effect = c.effect_id
        lines.append(f"Causal edge: {cause} → {effect} ({c.confidence:.0%})")

    # Similar past
    if similar:
        m = similar[0]
        lines.append(
            f"Similar past: {m.past_incident_id} ({m.similarity:.0%}) — {m.rationale}"
        )

    return "\n".join(lines)


def _bedrock(user_prompt: str) -> str:
    """Call AWS Bedrock Claude 3 Haiku with 4.5s timeout (G6)."""
    import boto3

    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(4.5)
    try:
        client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 150,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        response = client.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"].strip()
    finally:
        socket.setdefaulttimeout(old_timeout)


def _openrouter(user_prompt: str) -> str:
    """Call OpenRouter free Llama 3.1 8B with 4.5s timeout (G6)."""
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(4.5)
    try:
        payload = {
            "model": "meta-llama/llama-3.1-8b-instruct:free",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 150,
        }
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://archzos.com",
                "X-Title": "Drona",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    finally:
        socket.setdefaulttimeout(old_timeout)
