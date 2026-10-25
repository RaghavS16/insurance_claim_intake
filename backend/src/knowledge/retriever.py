"""Production RAG orchestration extracting requirements directly from authoritative policy and regulatory documents."""
from datetime import date
from src.agents.llm_factory import get_configured_llm, LLMTransientError, is_transient_llm_error
from .requirements import get_requirements_from_context
from .store import search, list_policy_documents, get_document_chunks, get_cached_requirement_manifest, save_requirement_manifest
from .reranker import rerank
from .policy_compiler import compile_policy_requirements, resolve_requirement_manifest
from src.config import settings


def infer_insurance_type_from_query(query: str) -> str | None:
    if not query:
        return None
    low = query.lower()
    # 1. Senior Citizen Health (must be evaluated before generic health)
    if any(k in low for k in ("senior citizen", "senior_citizen", "geriatric", "60 years", "age 60", "senior health", "60-75", "60–75")):
        return "senior_health"
    # 2. Motor
    if any(k in low for k in ("motor", "car", "vehicle", "auto", "two-wheeler", "bike", "accident", "garage", "idv", "own damage", "third-party")):
        return "motor"
    # 3. Health
    if any(k in low for k in ("health", "hospital", "medical", "cashless", "inpatient", "ayush", "tpa", "discharge summary", "rohini")):
        return "health"
    # 4. Home
    if any(k in low for k in ("home", "house", "property", "dwelling", "bharat griha", "burglary")):
        return "home"
    # 5. Travel
    if any(k in low for k in ("travel", "trip", "flight", "baggage", "passport", "overseas", "schengen", "pir")):
        return "travel"
    # 6. Cyber
    if any(k in low for k in ("cyber", "phishing", "ransomware", "upi", "unauthorized transaction", "1930", "ncrp", "cert-in")):
        return "cyber"
    return None

def rank_chunks_for_query(query: str, chunks: list[dict]) -> list[dict]:
    if not query or not chunks:
        return chunks
    low = query.lower()
    is_apply = any(w in low for w in ("apply", "application", "buy", "new policy", "proposal", "kyc", "documents required to apply"))
    is_claim = any(w in low for w in ("file", "filing", "how to claim", "claim process", "documents required", "checklist", "cashless", "reimbursement", "timeline", "surveyor", "fir", "intimation"))
    is_exclusions = any(w in low for w in ("exclusion", "not covered", "deductible", "depreciation", "waiting period", "moratorium", "co-pay", "sub-limit"))

    scored = []
    for c in chunks:
        score = float(c.get("rerank_score") or c.get("score") or 0.5)
        text = str(c.get("text") or "").lower()
        sec = str(c.get("section_number") or "").strip()
        cl = str(c.get("citation_label") or "").lower()

        # Section 5 boost for application queries
        if is_apply:
            if sec.startswith("5") or "5. how to apply" in text or "documents required to apply" in text or "section 5" in cl:
                score += 0.45
            elif "section 5" in text:
                score += 0.25

        # Section 6 boost for claim filing/document queries
        if is_claim:
            if sec.startswith("6") or "6. how to file a claim" in text or "claim intake form" in text or "mandatory documents checklist" in text or "settlement timeline" in text or "section 6" in cl:
                score += 0.45
            elif "section 6" in text or "settlement" in text:
                score += 0.25

        # Sections 2, 3, 4 boost for exclusions/deductibles
        if is_exclusions:
            if sec.startswith(("2", "3", "4")) or "exclusion" in text or "deductible" in text or "waiting period" in text or "moratorium" in text:
                score += 0.40

        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]

class KnowledgeRetriever:
    def retrieve(self, *, insurance_type: str | None = None, policy_number: str | None = None, incident_date: date | None = None, query: str = "", intake_channel: str = "insurer_web_portal", intake_started_at: str | None = None, claim_facts: dict | None = None, tenant_id: str | None = None, jurisdiction: str | None = None, claimant_id: str | None = None) -> dict:
        tenant_id = (tenant_id or "").strip()
        if not tenant_id:
            if settings.ENVIRONMENT == "test" and getattr(settings, "ALLOW_INSECURE_TEST_AUTH", False) is True:
                tenant_id = "test-tenant"
            else:
                tenant_id = "00000000-0000-0000-0000-000000000001"
        facts = dict(claim_facts or {})

        # Deterministic source-of-truth order:
        # 1. Exact Policy row from policy_number
        if policy_number and not insurance_type:
            try:
                from src.database.session import SessionLocal
                from src.database.models import Policy
                with SessionLocal() as db:
                    pol = db.query(Policy).filter(Policy.policy_number == policy_number).first()
                    if pol and pol.policy_type:
                        insurance_type = pol.policy_type
            except Exception:
                pass
        # 2. Authenticated claimant has exactly 1 active linked policy
        elif not policy_number and not insurance_type:
            claimant_user_id = claimant_id or facts.get("claimant_id")
            if claimant_user_id:
                try:
                    from src.database.session import SessionLocal
                    from src.database.models import Policy
                    with SessionLocal() as db:
                        pols = db.query(Policy).filter(
                            Policy.customer_id == str(claimant_user_id),
                            Policy.is_active == True,
                        ).all()
                        if len(pols) == 1:
                            policy_number = pols[0].policy_number
                            insurance_type = pols[0].policy_type
                except Exception:
                    pass

        # 3. Neither known -> attempt query-driven inference before giving up
        if not policy_number and not insurance_type:
            if query:
                inferred = infer_insurance_type_from_query(query)
                if inferred:
                    insurance_type = inferred
        if not policy_number and not insurance_type:
            return {
                "available": False,
                "status": "CONTEXT_RESOLUTION_REQUIRED",
                "reason": "POLICY_IDENTIFICATION_REQUIRED",
                "requirements": [],
                "evidence_requirements": [],
                "authoritative": False,
                "policy": [],
                "regulations": [],
                "question": "Could you provide your policy number or specify what type of policy (e.g., motor, health, home, travel) you are filing a claim for?",
            }

        incident_description = str(query or facts.get("event_description") or "").strip()
        searchable_facts = " ".join(
            f"{key}: {value}"
            for key, value in facts.items()
            if value not in (None, "", "UNKNOWN") and key not in {"event_description"}
        )
        q = " ".join(part for part in (insurance_type or "", incident_description, searchable_facts) if part).strip()[:4000]
        if not q:
            q = "insurance claim intake requirements and filing procedure"
        
        policy = []
        guidance = []
        manifest = []
        policy_docs = []
        policy_docs_found = False
        # Document-level compilation is authoritative when available, but a DB/cache
        # outage must not disable the existing retrieval path.
        try:
            policy_docs = list_policy_documents(insurance_type=insurance_type, policy_number=policy_number, incident_date=incident_date, tenant_id=tenant_id, jurisdiction=jurisdiction)
            policy_docs_found = bool(policy_docs)
            if not insurance_type and policy_docs:
                insurance_type = policy_docs[0].get("insurance_type")
            for doc in policy_docs:
                cached = get_cached_requirement_manifest(doc["document_id"], tenant_id)
                if not cached:
                    chunks = get_document_chunks(doc["document_id"], tenant_id)
                    try:
                        cached = compile_policy_requirements(document_id=doc["document_id"], insurance_type=insurance_type or "general", chunks=chunks)
                        if cached: save_requirement_manifest(doc["document_id"], cached, tenant_id)
                    except Exception:
                        from .policy_compiler import _extract_deterministic_manifest_from_chunks
                        cached = _extract_deterministic_manifest_from_chunks(chunks, insurance_type or "general", doc["document_id"])
                        if cached: save_requirement_manifest(doc["document_id"], cached, tenant_id)
                manifest.extend(cached)
        except Exception:
            manifest = []

        selected_policy_version = None
        if policy_docs:
            selected_policy_version = (policy_docs[0].get("policy_version") or (policy_docs[0].get("metadata") or {}).get("policy_version"))

        if manifest:
            manifest = list({str(x.get("key")): x for x in manifest if x.get("key")}.values())
            try:
                resolved = resolve_requirement_manifest(
                    manifest=manifest,
                    insurance_type=insurance_type,
                    claim_facts={**facts, "incident": incident_description},
                )
            except Exception:
                resolved = []
            if resolved:
                policy_hits = search(
                    q,
                    insurance_type=insurance_type,
                    policy_number=policy_number,
                    document_types=["policy_wording", "endorsement"],
                    incident_date=incident_date,
                    tenant_id=tenant_id,
                    jurisdiction=jurisdiction,
                )
                reg_hits = search(
                    q,
                    insurance_type=insurance_type,
                    document_types=["regulation", "guideline", "claim_requirement", "policy_regulatory"],
                    incident_date=incident_date,
                    tenant_id=tenant_id,
                    jurisdiction=jurisdiction,
                )
                if query:
                    policy_hits = rank_chunks_for_query(query, policy_hits)
                    reg_hits = rank_chunks_for_query(query, reg_hits)
                return {
                    "available": True,
                    "status": "OK",
                    "requirements": resolved,
                    "policy": policy_hits,
                    "regulations": reg_hits,
                    "authoritative": True,
                    "planning_model": "policy_manifest",
                    "policy_version": selected_policy_version,
                }

        # If an applicable policy wording exists, never replace a failed or unresolved
        # policy manifest with top-k semantic chunks and call that authoritative.
        # That was the source of the old "Claude sees the whole policy, our AI sees
        # five accident-similar chunks" behavior.
        if policy_docs_found:
            try:
                policy = search(
                    q,
                    insurance_type=insurance_type,
                    policy_number=policy_number,
                    document_types=["policy_wording", "endorsement"],
                    incident_date=incident_date,
                    tenant_id=tenant_id,
                    jurisdiction=jurisdiction,
                )
            except Exception:
                policy = []
            if policy:
                try:
                    fallback_reqs = get_requirements_from_context(chunks=policy, insurance_type=insurance_type)
                    if fallback_reqs:
                        resolved = resolve_requirement_manifest(
                            manifest=fallback_reqs,
                            insurance_type=insurance_type,
                            claim_facts={**facts, "incident": incident_description},
                        )
                        if resolved:
                            return {
                                "available": True,
                                "status": "OK",
                                "requirements": resolved,
                                "policy": policy,
                                "regulations": [],
                                "authoritative": True,
                                "planning_model": "chunk_manifest_fallback",
                                "policy_version": selected_policy_version,
                            }
                except Exception:
                    pass
            return {
                "available": False,
                "status": "POLICY_REQUIREMENT_MANIFEST_UNAVAILABLE",
                "requirements": [],
                "policy": policy,
                "regulations": [],
                "authoritative": False,
                "planning_model": "policy_manifest_required",
                "policy_version": selected_policy_version,
            }

        try:
            policy = search(q, insurance_type=insurance_type, policy_number=policy_number, document_types=["policy_wording", "endorsement"], incident_date=incident_date, tenant_id=tenant_id, jurisdiction=jurisdiction)
            guidance = search(q, insurance_type=insurance_type, document_types=["regulation", "guideline", "claim_requirement"], incident_date=incident_date, tenant_id=tenant_id, jurisdiction=jurisdiction)
        except Exception:
            policy, guidance = [], []

        if policy:
            try:
                policy = rerank(q, policy, top_n=5)
            except Exception:
                pass
        if guidance:
            try:
                guidance = rerank(q, guidance, top_n=5)
            except Exception:
                pass

        if not policy and not guidance:
            return {
                "available": False,
                "status": "NO_RELEVANT_KNOWLEDGE",
                "requirements": [],
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
                tenant_id=tenant_id,
                jurisdiction=jurisdiction,
            )
        except Exception as exc:
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
                    "authoritative": False,
                }
            requirements = []

        if not requirements:
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

    def answer_query(
        self,
        *,
        query: str,
        insurance_type: str | None = None,
        policy_number: str | None = None,
        incident_date: date | None = None,
        claim_facts: dict | None = None,
        top_k: int = 6,
        tenant_id: str | None = None,
        jurisdiction: str | None = None,
    ) -> dict:
        """Answer an arbitrary claimant question from retrieved policy/guidance evidence.

        This is deliberately separate from requirement planning. It is query-first:
        claimant questions can be answered before baseline confirmation or policy
        verification. No policy-specific assertion is generated without retrieved
        evidence.
        """
        question = " ".join((query or "").split()).strip()
        if not question:
            return {
                "answer": "Tell me what you would like to know about your insurance claim.",
                "grounded": False,
                "sources": [],
                "status": "EMPTY_QUERY",
            }

        tenant_id = (tenant_id or "").strip() or "00000000-0000-0000-0000-000000000001"
        if not insurance_type and question:
            inferred = infer_insurance_type_from_query(question)
            if inferred:
                insurance_type = inferred

        facts = dict(claim_facts or {})
        fact_context = " ".join(
            f"{key}: {value}"
            for key, value in facts.items()
            if value not in (None, "", "UNKNOWN")
            and key not in {"event_description"}
        )
        retrieval_query = " ".join(
            part for part in (question, insurance_type or "", fact_context) if part
        ).strip()[:4000]

        document_types = [
            "policy_wording",
            "endorsement",
            "regulation",
            "guideline",
            "claim_requirement",
        ]
        rows: list[dict] = []
        try:
            rows = search(
                retrieval_query,
                insurance_type=insurance_type,
                policy_number=policy_number,
                document_types=document_types,
                incident_date=incident_date,
                limit=max(top_k * 2, 8),
                tenant_id=tenant_id,
                jurisdiction=jurisdiction,
            )
        except Exception:
            rows = []

        # A general process question is still valid before the claimant supplies a
        # policy number/type. Broaden retrieval once rather than forcing intake first.
        if not rows and (insurance_type or policy_number):
            try:
                rows = search(
                    question,
                    document_types=document_types,
                    limit=max(top_k * 2, 8),
                    tenant_id=tenant_id,
                    jurisdiction=jurisdiction,
                )
            except Exception:
                rows = []

        if rows and question:
            rows = rank_chunks_for_query(question, rows)

        try:
            ranked = rerank(retrieval_query, rows, top_n=top_k) if rows else []
        except Exception:
            ranked = rows[:top_k]

        if ranked and question:
            ranked = rank_chunks_for_query(question, ranked)

        sources = [
            {
                key: row.get(key)
                for key in (
                    "chunk_id",
                    "document_id",
                    "source_name",
                    "source_uri",
                    "document_type",
                    "insurance_type",
                    "score",
                    "rerank_score",
                    "page_number",
                    "section_number",
                    "clause_number",
                    "citation_label",
                    "jurisdiction",
                    "document_version",
                    "text",
                )
                if row.get(key) is not None
            }
            for row in ranked
        ]
        if not sources:
            return {
                "answer": (
                    "I can help with the insurance process, but I do not have a matching "
                    "policy or claims-guidance source indexed for that question yet, so I "
                    "won't guess at a policy-specific answer. I can still help you collect "
                    "the details and documents needed for your claim."
                ),
                "grounded": False,
                "sources": [],
                "status": "NO_RELEVANT_KNOWLEDGE",
            }

        evidence_text = "\n\n".join(
            (
                f"[SOURCE {idx}] {row.get('source_name') or 'Unknown source'} "
                f"({row.get('document_type') or 'guidance'}; {row.get('citation_label') or 'citation unavailable'})\n"
                f"{str(row.get('text') or '')[:2500]}"
            )
            for idx, row in enumerate(sources, 1)
        )
        prompt = f"""You are the claimant-facing insurance RAG answerer.

Answer the claimant's actual question directly using ONLY the retrieved evidence below.
The claimant may ask a general process question, a policy question, a coverage question,
a document/evidence question, or a question about what happens next.

Rules:
- Answer the question first. Do not force a baseline questionnaire before answering.
- Treat retrieved policy wording as authoritative for policy-specific terms.
- Treat retrieved regulatory/guidance sources as authoritative for procedural or regulatory points.
- Never invent exclusions, coverage, limits, waiting periods, deadlines, reimbursement rules, or required documents.
- If the evidence does not establish a policy-specific answer, explicitly say that the indexed sources do not establish it.
- Do not copy the claimant's missing-field list into the answer.
- Keep the response clear and voice-friendly, normally 2 to 6 sentences.
- Every policy/coverage/deadline/evidence assertion must cite at least one supplied source using its citation_label. If citation_label is unavailable, explicitly say exact clause/page provenance is unavailable and do not present the statement as clause-supported.
- Intake collection is parallel work. Do not ask for claim details unless the question itself is about filing/processing
  or the caller is clearly continuing a claim; when you do ask, ask for only one useful next detail.

Claim context:
Insurance type: {insurance_type or "unknown"}
Policy number: {policy_number or "unknown"}
Incident date: {incident_date or "unknown"}

Retrieved evidence:
{evidence_text}

Claimant question:
{question}
"""
        try:
            result = invoke_with_retry(
                lambda: get_fast_llm().invoke(prompt),
                operation_name="claimant RAG question answering",
                attempts=1,
            )
            content = getattr(result, "content", result)
            if isinstance(content, list):
                answer = " ".join(
                    item if isinstance(item, str)
                    else str(item.get("text") or "")
                    for item in content
                    if isinstance(item, (str, dict))
                ).strip()
            else:
                answer = str(content or "").strip()
            if answer:
                labels = [
                    str(s.get("citation_label"))
                    for s in sources
                    if s.get("citation_label")
                ]
                if labels and not any(label in answer for label in labels):
                    answer = f"{answer}\n\nSources: {'; '.join(labels[:3])}"
                return {
                    "answer": answer,
                    "grounded": True,
                    "sources": sources,
                    "status": "OK",
                }
        except Exception:
            pass

        return {
            "answer": (
                "I found relevant insurance guidance, but the answer service is temporarily "
                "unavailable. I won't guess at the policy-specific details."
            ),
            "grounded": False,
            "sources": sources,
            "status": "LLM_TEMPORARILY_UNAVAILABLE",
        }
