"""Production RAG orchestration with whole-policy requirement compilation and claim-time resolution."""
from datetime import date
from src.agents.llm_factory import LLMTransientError, get_configured_llm, get_fast_llm, is_transient_llm_error
from .requirements import get_requirements_from_context, get_provisional_requirements
from .requirement_compiler import get_or_compile_policy_manifest
from .store import search
from .reranker import rerank

class KnowledgeRetrievalError(RuntimeError):
    pass

def _dedupe(rows: list[dict]) -> list[dict]:
    seen = set()
    output = []
    for row in rows:
        key = str(row.get("chunk_id") or row.get("id") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        output.append(row)
    return output

class KnowledgeRetriever:
    def retrieve(
        self, *, insurance_type: str, policy_number: str | None = None,
        incident_date: date | None = None, query: str = "",
        intake_channel: str = "insurer_web_portal",
        intake_started_at: str | None = None,
        claim_facts: dict | None = None,
    ) -> dict:
        facts = dict(claim_facts or {})
        incident_description = str(query or facts.get("event_description") or "").strip()
        searchable_facts = " ".join(
            f"{key}: {value}"
            for key, value in facts.items()
            if value not in (None, "", "UNKNOWN") and key not in {"event_description"}
        )
        claim_query = " ".join(
            part for part in (insurance_type, incident_description, searchable_facts) if part
        ).strip()[:4000]
        if not insurance_type:
            return {"available": False, "status": "INVALID_CONTEXT", "requirements": [], "policy": [], "regulations": []}

        # Compile the complete policy once and cache its requirement manifest. This is
        # deliberately independent from the accident embedding query: a policy clause
        # can be a critical claim requirement even when it is semantically unrelated
        # to the claimant's narrative.
        policy_manifest = None
        try:
            policy_manifest = get_or_compile_policy_manifest(
                insurance_type=insurance_type,
                policy_number=policy_number,
                incident_date=incident_date,
            )
        except Exception:
            policy_manifest = None

        # Supporting retrieval now includes requirement-oriented queries as well as the
        # claimant narrative. The manifest remains the source of truth for the inventory.
        support_queries = [
            claim_query,
            f"{insurance_type} claim requirements claim procedure notification evidence",
            f"{insurance_type} claims documents conditions third party accident damage",
        ]
        policy_rows: list[dict] = []
        guidance_rows: list[dict] = []
        try:
            for support_query in support_queries:
                if not support_query:
                    continue
                policy_rows.extend(
                    search(
                        support_query,
                        insurance_type=insurance_type,
                        policy_number=policy_number,
                        document_types=["policy_wording"],
                        incident_date=incident_date,
                    )
                )
                guidance_rows.extend(
                    search(
                        support_query,
                        insurance_type=insurance_type,
                        document_types=["regulation", "guideline", "claim_requirement"],
                        incident_date=incident_date,
                    )
                )
        except Exception:
            pass

        policy = _dedupe(policy_rows)
        guidance = _dedupe(guidance_rows)
        if policy:
            try:
                policy = rerank(
                    f"{insurance_type} claim requirements {claim_query}",
                    policy,
                    top_n=12,
                )
            except Exception:
                policy = policy[:12]
        if guidance:
            try:
                guidance = rerank(
                    f"{insurance_type} claim requirements {claim_query}",
                    guidance,
                    top_n=12,
                )
            except Exception:
                guidance = guidance[:12]

        # A cached document-level manifest is authoritative even if the current
        # accident query finds no similar policy chunk.
        if policy_manifest:
            try:
                llm = get_configured_llm()
                requirements = get_requirements_from_context(
                    llm,
                    insurance_type=insurance_type,
                    policy_context=policy,
                    regulatory_context=guidance,
                    incident_description=incident_description,
                    intake_channel=intake_channel,
                    intake_started_at=intake_started_at,
                    claim_facts=facts,
                    policy_manifest=policy_manifest,
                )
            except Exception as exc:
                try:
                    fast_llm = get_fast_llm()
                    requirements = get_requirements_from_context(
                        fast_llm,
                        insurance_type=insurance_type,
                        policy_context=policy,
                        regulatory_context=guidance,
                        incident_description=incident_description,
                        intake_channel=intake_channel,
                        intake_started_at=intake_started_at,
                        claim_facts=facts,
                        policy_manifest=policy_manifest,
                    )
                except Exception:
                    requirements = []
                if requirements:
                    return {
                        "available": True,
                        "status": "OK",
                        "requirements": requirements,
                        "policy": policy,
                        "regulations": guidance,
                        "policy_manifest": policy_manifest,
                        "authoritative": True,
                        "planning_model": "reasoning_fallback",
                    }
                # If the resolver is unavailable, use the cached source-grounded
                # manifest directly. This is safer than falling back to a generic
                # industry checklist and still blocks submission on unresolved items.
                manifest_items = policy_manifest.get("requirements") or []
                if manifest_items:
                    return {
                        "available": True,
                        "status": "OK",
                        "requirements": manifest_items,
                        "policy": policy,
                        "regulations": guidance,
                        "policy_manifest": policy_manifest,
                        "authoritative": True,
                        "planning_model": "cached_manifest",
                    }
                transient_text = str(exc).lower()
                if isinstance(exc, LLMTransientError) or is_transient_llm_error(exc) or any(
                    token in transient_text
                    for token in ("503", "429", "timeout", "temporarily unavailable", "rate limit", "overloaded")
                ):
                    return {
                        "available": False,
                        "status": "LLM_TEMPORARILY_UNAVAILABLE",
                        "requirements": [],
                        "policy": policy,
                        "regulations": guidance,
                        "policy_manifest": policy_manifest,
                        "authoritative": True,
                    }

        if not policy and not guidance:
            try:
                provisional_llm = get_fast_llm()
            except Exception:
                provisional_llm = None
            provisional = get_provisional_requirements(
                provisional_llm,
                insurance_type=insurance_type,
                claim_facts={
                    **facts,
                    "policy_number": policy_number,
                    "incident_date": str(incident_date) if incident_date else None,
                    "incident": incident_description,
                },
                conversation=incident_description,
            )
            return {
                "available": bool(provisional),
                "status": "PROVISIONAL" if provisional else "NO_RELEVANT_KNOWLEDGE",
                "requirements": provisional,
                "policy": [],
                "regulations": [],
                "authoritative": False,
            }

        try:
            llm = get_configured_llm()
            requirements = get_requirements_from_context(
                llm,
                insurance_type=insurance_type,
                policy_context=policy,
                regulatory_context=guidance,
                incident_description=incident_description,
                intake_channel=intake_channel,
                intake_started_at=intake_started_at,
                claim_facts=facts,
            )
        except Exception as exc:
            try:
                fast_llm = get_fast_llm()
                requirements = get_requirements_from_context(
                    fast_llm,
                    insurance_type=insurance_type,
                    policy_context=policy,
                    regulatory_context=guidance,
                    incident_description=incident_description,
                    intake_channel=intake_channel,
                    intake_started_at=intake_started_at,
                    claim_facts=facts,
                )
            except Exception:
                requirements = []
            if requirements:
                return {
                    "available": True,
                    "status": "OK",
                    "requirements": requirements,
                    "policy": policy,
                    "regulations": guidance,
                    "authoritative": True,
                    "planning_model": "reasoning_fallback",
                }

            provisional = get_provisional_requirements(
                fast_llm if "fast_llm" in locals() else None,
                insurance_type=insurance_type,
                claim_facts={
                    **facts,
                    "policy_number": policy_number,
                    "incident_date": str(incident_date) if incident_date else None,
                    "incident": incident_description,
                },
                conversation=incident_description,
            )
            if provisional:
                return {
                    "available": True,
                    "status": "PROVISIONAL",
                    "requirements": provisional,
                    "policy": policy,
                    "regulations": guidance,
                    "authoritative": False,
                    "planning_model": "provisional_fallback",
                }

            transient_text = str(exc).lower()
            if "HF_TOKEN is required" in str(exc) or "API key" in str(exc):
                return {
                    "available": False,
                    "status": "LLM_CONFIGURATION_UNAVAILABLE",
                    "requirements": [],
                    "policy": policy,
                    "regulations": guidance,
                    "authoritative": False,
                }
            if (
                isinstance(exc, LLMTransientError)
                or is_transient_llm_error(exc)
                or any(token in transient_text for token in ("503", "429", "timeout", "temporarily unavailable", "rate limit", "overloaded"))
            ):
                return {
                    "available": False,
                    "status": "LLM_TEMPORARILY_UNAVAILABLE",
                    "requirements": [],
                    "policy": policy,
                    "regulations": guidance,
                }
            requirements = []

        if not requirements:
            provisional = get_provisional_requirements(
                None,
                insurance_type=insurance_type,
                claim_facts={
                    **facts,
                    "policy_number": policy_number,
                    "incident_date": str(incident_date) if incident_date else None,
                    "incident": incident_description,
                },
                conversation=incident_description,
            )
            if provisional:
                return {
                    "available": True,
                    "status": "PROVISIONAL",
                    "requirements": provisional,
                    "policy": policy,
                    "regulations": guidance,
                    "authoritative": False,
                }
            return {
                "available": False,
                "status": "REQUIREMENT_PLAN_UNAVAILABLE",
                "requirements": [],
                "policy": policy,
                "regulations": guidance,
                "authoritative": False,
            }

        return {
            "available": True,
            "status": "OK",
            "requirements": requirements,
            "policy": policy,
            "regulations": guidance,
            "authoritative": True,
        }
