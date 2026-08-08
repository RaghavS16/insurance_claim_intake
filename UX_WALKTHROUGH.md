# User Experience Walkthrough — Final System (Post-October)
## All Paths Through the 7-Step Workflow (Corrected)

> **⚠️ REVIEW PANEL NOTE — August (Review 1) milestone:**
> This document describes the **target-state** system (post-October). Features marked
> with 🎤 (voice), 📋 (policy clause citations), 💸 (appeal workflow), and ⭐ (feedback)
> are **not yet implemented** in the August codebase. Do NOT demo these paths as live
> capabilities in Review 1.
>
> **What IS live in August (text-only pipeline):**
> - ✅ Text claim intake, multi-turn field-prompt loop
> - ✅ Document upload (S3), type validation
> - ✅ Policy validation (active/expired), claim_type vs policy_type check
> - ✅ Coverage check (amount-only — clause citations are September RAG work)
> - ✅ Rule-based fraud detection (future date, near-limit amount)
> - ✅ Adjuster routing with load-balancing
> - ✅ Auto-approve / deny / flag / manual-review decisions
>
> **Explicitly out of scope for August:**
> - 🔜 Voice input/output (September)
> - 🔜 Policy clause citations in approval messages (September RAG)
> - 🔜 Scope-of-coverage exclusion enforcement, e.g. "flood excluded under clause 2.1" (September)
> - 🔜 Appeal / reopening workflow (October)
> - 🔜 Feedback collection (October)
> - 🔜 Customer identity / ownership check (October)

Every scenario below is voice-first with text fallback (🎤 = spoken, 💬 = also shown as text on screen).

---

## **PATH 1: Happy Path — Simple Auto-Approved Claim**

```
🎤 User: "My car was hit by a truck on July 15th. Policy XYZ123.
          Repair cost is fifty thousand rupees."

💬 System (screen): Transcribing... 

🎤 System: "I heard: your car was damaged on July 15, 2025, under
            policy XYZ123, with a repair cost of ₹50,000. Is that correct?"
💬 System (screen):
   ┌─────────────────────────────────┐
   │ Incident Date: 2025-07-15       │
   │ Policy: XYZ123                  │
   │ Claim Type: Auto                │
   │ Damage: Vehicle collision       │
   │ Amount: ₹50,000                 │
   │ [✓ Confirm]  [✎ Edit]          │
   └─────────────────────────────────┘

🎤 User: "Yes, that's correct."

🎤 System: "Please upload photos of the damage and a repair estimate."
💬 System (screen): [Upload damage_photo] [Upload repair_estimate]

User: [uploads 2 photos + 1 PDF estimate]

💬 System (screen): "✓ damage_photo received  ✓ repair_estimate received"

🎤 System: "Thank you. Checking your policy and evaluating your claim..."
💬 System (screen): [Loading: Validating policy → Checking coverage → Assessing risk]

🎤 System: "Good news — your claim is approved. This collision is
            covered under clause 3.1 of your policy. After your ₹5,000
            deductible, your payout amount is ₹45,000. Your ticket
            number is CLAIM-A1B2C3D4. Priya Sharma is your auto claims
            contact if you have any questions — you don't need to do
            anything further; this has been logged for processing."
💬 System (screen):
   ┌─────────────────────────────────┐
   │ ✅ APPROVED                     │
   │ Ticket: CLAIM-A1B2C3D4          │
   │ Payout: ₹45,000 (after ₹5,000   │
   │         deductible)             │
   │ Your contact: Priya Sharma      │
   │ Policy clause cited: 3.1        │
   │ Status: Closed                  │
   └─────────────────────────────────┘

[A few days later, in-app]
💬 System: "How was your claim experience?"
   ⭐⭐⭐⭐⭐  [Comment box]  [Submit]
```

**Operational clarification:** Approval does **not** place this claim in Priya's active work queue. Nothing needs her sign-off — the decision engine already approved it. She's attached to the record as the claimant's named point of contact for questions or follow-up, purely informational. See Path 10 for the contrast with claims that *do* require an adjuster's action.

---

## **PATH 2: Text-Only User (Voice Declined)**

```
💬 System (screen): [🎤 Speak your claim]  [⌨️ Type instead]

User: [clicks "Type instead"]

💬 System (screen): [Text box: "Describe what happened..."]

User types: "Home flooded during heavy rain on June 3. Policy HOME456.
             Damage estimate is ₹150,000."

[Everything below happens identically to Path 1, but entirely in text —
no TTS is triggered, no microphone is used, all system responses are
displayed as text only.]

💬 System (screen): Extracted fields shown for confirmation → [Confirm] [Edit]
💬 System (screen): Document upload prompt (text, no speech)
💬 System (screen): Decision shown as text card
```
**Note:** `input_mode = "text"` is passed through the entire pipeline; TTS is simply skipped, not attempted-then-hidden.

---

## **PATH 3: Missing Mandatory Fields — Multi-Turn Prompt Loop**

```
🎤 User: "My car got damaged."

🎤 System: "I need a bit more information. What is your policy number?"
💬 System (screen): [Text field also available: "Policy number"]

🎤 User: "XYZ123."

🎤 System: "Thank you. What date did the incident occur?"

🎤 User: "July 15th."

🎤 System: "Got it. What's the estimated repair cost?"

🎤 User: "About fifty thousand rupees."

🎤 System: "Perfect, I have everything I need. Let me read that back to you..."
   [Proceeds to Confirmation step, same as Path 1]
```
**Edge case handled:** each answer is appended and re-extracted — the user is never asked for a field they already gave, even out of order.

---

## **PATH 4: Wrong/Irrelevant Document Uploaded**

```
[Continuing from confirmation in Path 1]

🎤 System: "Please upload photos of the damage and a repair estimate."

User: [accidentally uploads a medical bill PDF, tagged as "repair_estimate"]

💬 System (screen):
   ┌─────────────────────────────────────────────┐
   │ ⚠️ This doesn't look like a repair estimate. │
   │ Please re-upload the correct document.       │
   │ Required: damage photos, repair estimate      │
   └─────────────────────────────────────────────┘
🎤 System: "That document doesn't appear to match a repair estimate.
            Could you upload the correct one?"

User: [uploads correct repair estimate PDF]

💬 System (screen): "✓ repair_estimate received"
[Continues normally]
```
**September+ behavior:** rejection is content-based (OCR reads the doc and checks it plausibly matches the type), not just filename/label matching.

---

## **PATH 5: Claim Type Needs No Documents (Business Interruption)**

```
🎤 User: "I want to file a business interruption claim under policy
          BIZ001. Estimated loss is ₹200,000 due to a supplier delay
          on August 2nd."

[Fields confirmed as usual]

💬 System (screen): "No supporting documents are required for this
                      claim type. Proceeding to evaluation."
🎤 System: "This claim type doesn't require document uploads, so I'll
            go ahead and evaluate it now."

[Skips straight to policy validation → risk assessment → decision]

🎤 System: "Your claim is approved. Supplier delay is covered under
            clause 4.2 of your business policy. After your ₹10,000
            deductible, your payout amount is ₹190,000. Your ticket
            is CLAIM-B7C6D5E4."
💬 System (screen):
   ┌─────────────────────────────────┐
   │ ✅ APPROVED                     │
   │ Ticket: CLAIM-B7C6D5E4          │
   │ Payout: ₹190,000                │
   │ Status: Closed                  │
   └─────────────────────────────────┘

[Feedback prompt fires, same as any closed claim]
```
**Edge case handled:** `document_requirement_checker` sees `DOCUMENT_REQUIREMENTS["business"] = []` and skips the upload step entirely — no dead-end, no unnecessary prompt. **This scenario resolves exactly like Path 1 from Policy Validation onward** — the same `approved` / `denied` / `flagged_for_review` outcomes are all still possible for a document-free claim type; it just never pauses for uploads along the way. This case is now correctly included in the summary table below (it was omitted before).

---

## **PATH 6: Claim Denied — Not Covered**

```
🎤 User: "My basement flooded during monsoon season. Policy HOME456.
          Damage is about ₹150,000."

[Fields confirmed, documents uploaded]

🎤 System: "I'm sorry, but this claim cannot be approved. Flood damage
            is excluded under clause 2.1 of your policy, which covers
            fire, theft, and structural damage but not water intrusion
            from external flooding. This decision is final in our
            system. If you believe this is incorrect, you can request
            a human appeal review within 30 days — that opens a
            separate case with an adjuster; it does not reopen this
            claim automatically."
💬 System (screen):
   ┌─────────────────────────────────┐
   │ ❌ DENIED                        │
   │ Reason: Flood damage excluded    │
   │         (Policy clause 2.1)      │
   │ Status: Closed                   │
   │ (Automated decision — no further │
   │  action happens unless you       │
   │  request an appeal)              │
   │ [Request appeal review →]        │
   └─────────────────────────────────┘

[Feedback prompt still appears, even for denials]
💬 System: "We'd still like your feedback on this experience."
```

**Fix — the conflict:** `closed` means **the automated pipeline's decision is final and no further automated action occurs on this ticket**, not that the claimant has no recourse. "Closed" and "appealable" aren't contradictory — closure ends the *system's* workflow on this record; requesting an appeal explicitly creates a **new, separate manual-review case** (its own ticket, referencing the original), rather than silently reopening it. The button is labeled "Request appeal review," not "Reopen claim," and both the spoken response and the on-screen text now say this explicitly, so there's no implication that "closed" claims sit in limbo waiting on a 30-day window.

---

## **PATH 7: High Fraud/Risk Score — Flagged for Manual Review**

```
🎤 User: "My car was damaged on January 1st, 2027. Policy XYZ123.
          Repair cost is ₹480,000."

[System notices this is a future date — but doesn't reject outright,
 evaluation proceeds]

🎤 System: "Your claim requires additional review due to some unusual
            details. It's been placed in our review team's queue —
            Anita Desai, our complex claims specialist, will contact
            you within 48 hours to verify the details. This is not a
            denial — just a closer look before a final decision."
💬 System (screen):
   ┌─────────────────────────────────┐
   │ ⚠️ FLAGGED FOR REVIEW           │
   │ Ticket: CLAIM-F9E8D7C6           │
   │ Assigned to: Anita Desai         │
   │ (action required from her)       │
   │ Status: Pending review           │
   │         (NOT closed)             │
   │ [View what triggered this flag]  │
   └─────────────────────────────────┘

[No feedback prompt yet — feedback only fires once closure_status = closed]

[Days later, after adjuster resolves it manually — see Path 10 — the
 record updates and closure/feedback triggers then]
```
**Critical edge case handled:** flagged claims stay open, don't get a false "closed" status, and feedback is deferred until an actual human decision closes the file. Unlike Path 1's Priya, Anita's assignment here means **action is required from her** — see Path 10 for the explicit contrast.

---

## **PATH 8: Invalid or Expired Policy**

```
🎤 User: "My car was damaged. Policy AUTO789. Cost is ₹20,000."

[Fields confirmed]

🎤 System: "I'm unable to validate this policy — it appears to be
            expired or inactive. This has been placed in our team's
            queue so they can check your account directly. You'll
            hear back within one business day."
💬 System (screen):
   ┌─────────────────────────────────┐
   │ ⚠️ MANUAL REVIEW REQUIRED       │
   │ Reason: Policy could not be     │
   │         validated                │
   │ Status: Pending review           │
   └─────────────────────────────────┘
```
**Edge case handled:** this never reaches document upload, coverage check, or fraud check — policy validation fails fast, exactly like your original test suite expects.

---

## **PATH 9: User Declines to Confirm Extracted Details**

```
💬 System (screen): Extracted fields shown
   [✓ Confirm]  [✎ Edit]

User: [clicks Edit — says the amount is wrong]

🎤 System: "No problem — what's the correct amount?"

🎤 User: "It's actually sixty thousand, not fifty."

💬 System (screen): Amount field updates to ₹60,000, shown again for confirmation

User: [clicks Confirm]

[Proceeds normally]
```
**Edge case handled:** confirmation isn't a rubber stamp — the user can correct any field before evaluation runs, preventing a wrong decision on bad data.

---

## **PATH 10: Adjuster-Side Experience — Active Queue vs. Informational Assignment**

Two different things happen to two different adjusters, and they are **not the same UX**:

### **10a. Priya Sharma (auto specialist) — Path 1's approved claim**
```
💬 Dashboard — Priya's view:
   ┌─────────────────────────────────────────┐
   │ My Contacts (informational — no action   │
   │ required)                                 │
   │                                            │
   │ CLAIM-A1B2C3D4 — ✅ Approved — Closed    │
   │   Payout: ₹45,000 (logged, not disbursed  │
   │   by this system)                         │
   │   [View claim — read only]                │
   └─────────────────────────────────────────┘
```
Priya has **nothing to click, approve, or unlock**. The claim already reached `closed`. She's listed because she's the claimant's named contact if they call in with questions — this is a CRM-style relationship record, not a task.

### **10b. Anita Desai (complex claims specialist) — Path 7's flagged claim**
```
💬 Dashboard — Anita's view:
   ┌─────────────────────────────────────────┐
   │ My Active Queue (3 claims need action)    │
   │                                            │
   │ CLAIM-F9E8D7C6 — ⚠️ Flagged — Auto       │
   │   Fraud flags: future_incident_date,      │
   │                 claim_near_policy_limit    │
   │   Status: Pending review — awaiting your   │
   │           decision                         │
   │   [Open claim to review →]                 │
   └─────────────────────────────────────────┘

[Anita clicks in]

💬 Claim Detail View:
   - Extracted fields (as confirmed by claimant)
   - Uploaded documents (viewable inline)
   - Fraud flags + reasoning
   - Coverage check result + cited policy clauses
   - [Mark Approved] [Mark Denied] [Request more info from claimant]

[Anita reviews, calls claimant, verifies details, clicks "Mark Approved"]

→ closure_status flips from pending_review to closed
→ claimant receives final decision (spoken + text, same format as Path 1)
→ feedback prompt fires
```
Anita's queue **only contains claims where `final_decision = flagged_for_review` or `manual_review`** — i.e., where the automated pipeline explicitly could not decide and a human must act. Approved/denied claims never appear here as actionable items; they may still be visible read-only, exactly as in Priya's view.

---

## **Summary Table: Every Outcome and Its UX (Corrected)**

| Scenario | final_decision | closure_status | Adjuster action needed? | User sees | Feedback fires? |
|---|---|---|---|---|---|
| Fields incomplete | `need_more_info` | `awaiting_user` | No | Spoken + text prompt for missing field | No |
| Docs incomplete | `need_documents` | `awaiting_user` | No | Spoken + text prompt to upload | No |
| Wrong document type | *(rejected before state changes)* | — | No | Inline error, re-upload prompt | No |
| No docs required → approved (Path 5) | `approved` | `closed` | No — informational contact only | Approval + payout + contact name | **Yes** |
| No docs required → denied | `denied` | `closed` | No | Denial + policy citation + appeal button | **Yes** |
| No docs required → flagged | `flagged_for_review` | `pending_review` | **Yes** | "Routed for review" message | No (until closed) |
| Policy invalid/expired | `manual_review` | `pending_review` | **Yes** | "Sent to our team" message | No (until closed) |
| Not covered | `denied` | `closed` | No | Denial + policy citation + **separate appeal-request button** (does not reopen this ticket) | **Yes** |
| High fraud/risk | `flagged_for_review` | `pending_review` | **Yes** — active queue item | "Routed for review" message | No (until closed) |
| Covered + low risk | `approved` | `closed` | No — assigned adjuster is informational only | Approval + payout + contact name | **Yes** |
| Adjuster resolves flagged claim | *(adjuster sets outcome)* | `closed` | Action was just taken | Final decision delivered, same format as auto-path | **Yes** |
| Claimant requests appeal on a denial | *(new case created)* | Original stays `closed`; new case starts `pending_review` on a **new ticket** | **Yes**, on the new ticket | "Appeal case opened: CLAIM-XXXX" | No (until new case closes) |

---

## **What Changed From the Previous Version**

1. **Denial/appeal conflict fixed** — `closed` now explicitly means "the automated decision is final on this ticket," and appeals are reframed as opening a *new* linked case rather than implying the original claim silently stays open for 30 days. Both spoken and on-screen text now say this consistently.
2. **Path 5 added to the summary table** — a document-free claim type isn't its own outcome; it's a routing shortcut that still ends in `approved` / `denied` / `flagged_for_review` like any other claim. The table now shows all three possibilities for that path instead of omitting it.
3. **Adjuster queue semantics clarified** — added an explicit "Adjuster action needed?" column, and Path 10 is now split into 10a (informational contact, Priya) and 10b (active queue, Anita) so it's unambiguous that only `flagged_for_review` / `manual_review` claims require an adjuster to click anything.

---

## **What Makes This "Complete" for Your Viva**

Every edge case above maps to a real, tested code path in your refactored pipeline:
- Multi-turn field prompting → `mandatory_field_checker`
- Document rejection/skip logic → `document_requirement_checker`
- Denial with citation + separate appeal path → `coverage_checker` + `response_formatter` + a new appeal-case endpoint (October scope, creates a new `claim` row referencing the original via `appealed_claim_id`)
- Flagged ≠ closed, and only flagged/manual_review claims populate an adjuster's **active** queue → `fraud_detector` + `closure_status` branching + dashboard query filtered on `final_decision IN ('flagged_for_review', 'manual_review')`
- Approved/denied claims appear in an adjuster's dashboard as **read-only/informational**, never as actionable queue items → dashboard query separates `assigned_adjuster` (contact) from `requires_action` (queue)
- Policy fail-fast → `policy_validator` conditional edge
- Editable confirmation → frontend state before `/confirm` is called

No path in this walkthrough requires payment processing — every outcome ends at routing, closure, or feedback, consistent with your scoping decision.
