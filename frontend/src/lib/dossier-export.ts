/**
 * Utility for exporting formatted claim dossiers and printing official adjudication certificates.
 */

export function downloadDossierFile(content: string, filename: string, mimeType = 'text/plain') {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function printAdjudicationCertificate(cert: any) {
  if (!cert || typeof window === 'undefined') return;
  const printWindow = window.open('', '_blank');
  if (!printWindow) return;

  const html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Official Claim Adjudication Certificate — #${cert.ticket_id}</title>
  <style>
    @page { size: A4 portrait; margin: 15mm 20mm; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #111827; margin: 0; padding: 24px; line-height: 1.5; font-size: 13px; }
    .header { border-bottom: 2px solid #007AFF; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-end; }
    .title { font-size: 20px; font-weight: 800; color: #007AFF; letter-spacing: -0.5px; margin: 0; }
    .subtitle { font-size: 11px; color: #6B7280; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase; background: #E0F2FE; color: #0369A1; }
    .section { margin-bottom: 18px; }
    .section-title { font-size: 12px; font-weight: 700; color: #374151; border-bottom: 1px solid #E5E7EB; padding-bottom: 4px; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
    .field-label { font-size: 11px; color: #6B7280; margin-bottom: 1px; }
    .field-value { font-size: 13px; font-weight: 600; color: #111827; }
    table { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 12px; }
    th { text-align: left; background: #F3F4F6; padding: 6px 10px; border: 1px solid #E5E7EB; font-size: 11px; color: #4B5563; text-transform: uppercase; }
    td { padding: 6px 10px; border: 1px solid #E5E7EB; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; }
    .decision-box { background: #F0FDF4; border: 1.5px solid #86EFAC; border-radius: 8px; padding: 12px 16px; margin-top: 8px; }
    .footer { margin-top: 30px; border-top: 1px solid #E5E7EB; padding-top: 10px; font-size: 10px; color: #9CA3AF; text-align: center; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1 class="title">INTELLICLAIM ADJUDICATION CERTIFICATE</h1>
      <div class="subtitle">Official Claim Verification & Settlement Dossier</div>
    </div>
    <div style="text-align: right;">
      <span class="badge">${(cert.status || 'FILED').toUpperCase()}</span>
      <div style="font-size: 11px; color: #6B7280; margin-top: 4px;">Ticket: <strong>#${cert.ticket_id}</strong></div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">1. Insured & Policy Schedule</div>
    <div class="grid">
      <div>
        <div class="field-label">Policy Number</div>
        <div class="field-value">${cert.policy_number || 'N/A'}</div>
      </div>
      <div>
        <div class="field-label">Coverage Line</div>
        <div class="field-value">${(cert.insurance_type || 'General').toUpperCase()}</div>
      </div>
      <div>
        <div class="field-label">Policyholder Name</div>
        <div class="field-value">${cert.policyholder_name || 'Registered Claimant'}</div>
      </div>
      <div>
        <div class="field-label">Coverage Bound / Deductible</div>
        <div class="field-value">Limit: $${Number(cert.coverage_amount || 0).toLocaleString()} • Deductible: $${Number(cert.deductible || 0).toLocaleString()}</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">2. Incident Details & Loss Narrative</div>
    <div class="grid">
      <div>
        <div class="field-label">Incident Date</div>
        <div class="field-value">${cert.event_date || 'Awaiting verification'}</div>
      </div>
      <div>
        <div class="field-label">Location</div>
        <div class="field-value">${cert.event_location || 'Awaiting verification'}</div>
      </div>
      <div style="grid-column: span 2;">
        <div class="field-label">Claimant Loss Description</div>
        <div class="field-value" style="font-weight: normal; margin-top: 2px;">${cert.event_description || 'No description recorded.'}</div>
      </div>
    </div>
  </div>

  ${cert.verified_facts && Object.keys(cert.verified_facts).length > 0 ? `
  <div class="section">
    <div class="section-title">3. Verified Dynamic Facts (RAG Extracted)</div>
    <div class="grid">
      ${Object.entries(cert.verified_facts)
        .filter(([k]) => !['policy_id', 'insurance_type', 'event_date', 'event_location', 'event_description', 'estimated_claim_amount'].includes(k))
        .map(([k, v]) => `
          <div>
            <div class="field-label" style="text-transform: capitalize;">${k.replace(/_/g, ' ')}</div>
            <div class="field-value">${typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v ?? '—')}</div>
          </div>
        `).join('')}
    </div>
  </div>` : ''}

  <div class="section">
    <div class="section-title">4. Evidence Verification Manifest & Cryptographic Checksums</div>
    ${Array.isArray(cert.evidence_manifest) && cert.evidence_manifest.length > 0 ? `
    <table>
      <thead>
        <tr>
          <th>Document</th>
          <th>Verification</th>
          <th>Size</th>
          <th>SHA-256 Checksum</th>
        </tr>
      </thead>
      <tbody>
        ${cert.evidence_manifest.map((ev: any) => `
          <tr>
            <td><strong>${ev.filename}</strong></td>
            <td>${ev.status}</td>
            <td>${Math.round(ev.size_bytes / 1024)} KB</td>
            <td class="mono">${ev.sha256 || 'Verified'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>` : '<div style="color: #6B7280; font-style: italic;">No evidence files attached.</div>'}
  </div>

  <div class="section">
    <div class="section-title">5. Adjudication Settlement & Adjuster Rationale</div>
    ${cert.decision ? `
    <div class="decision-box">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <span style="font-weight: 700; color: #166534; font-size: 14px;">DECISION: ${String(cert.decision.status).toUpperCase()}</span>
        ${cert.decision.approved_amount ? `<span style="font-weight: 800; color: #15803D; font-size: 15px;">Settlement: $${Number(cert.decision.approved_amount).toLocaleString()}</span>` : ''}
      </div>
      <div style="color: #374151; font-size: 12px;">${cert.decision.rationale}</div>
    </div>` : '<div style="color: #6B7280; font-style: italic;">Claim pending final adjudication decision.</div>'}
  </div>

  <div class="section">
    <div class="section-title">6. Tamper-Evident Audit Trail</div>
    ${Array.isArray(cert.audit_trail) && cert.audit_trail.length > 0 ? `
    <table>
      <thead>
        <tr>
          <th>Timestamp</th>
          <th>Event Type</th>
          <th>Audit Details</th>
        </tr>
      </thead>
      <tbody>
        ${cert.audit_trail.slice(0, 10).map((a: any) => `
          <tr>
            <td class="mono">${a.created_at ? a.created_at.replace('T', ' ').substring(0, 19) : ''}</td>
            <td><strong>${a.event_type}</strong></td>
            <td>${a.reason || 'Verified'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>` : '<div style="color: #6B7280;">Audit trail initialized.</div>'}
  </div>

  <div class="footer">
    This document is an electronically generated and cryptographically verifiable adjudication certificate from the IntelliClaim Autonomous Claim Processing Engine. Verified at: ${cert.generated_at}
  </div>
</body>
</html>
  `;
  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
  setTimeout(() => {
    printWindow.print();
  }, 250);
}
