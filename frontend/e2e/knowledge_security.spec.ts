import { test, expect } from '@playwright/test';

test.describe('Knowledge Management, RBAC Security & IDOR Isolation', () => {

  test('Knowledge Ingestion, Vector Indexing and Semantic Retrieval', async ({ request }) => {
    // Login as Adjuster
    const loginRes = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: {
        email: 'asha.adjuster@insurance.com',
        password: 'DemoPassword123!'
      }
    });
    expect(loginRes.ok()).toBeTruthy();
    const token = (await loginRes.json()).access_token;

    // 1. Ingest new policy wording clause
    const uniqueClause = `Special Endorsement Section 99.B: High-altitude mountain terrain operations are covered up to INR 25,00,000 subject to mandatory snow chain certification #${Date.now()}.`;
    const ingestRes = await request.post('http://localhost:8000/api/v1/knowledge/documents', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        source_name: `Himalayan-Terrain-Endorsement-${Date.now()}.txt`,
        text: uniqueClause,
        document_type: 'policy_wording',
        insurance_type: 'motor',
        jurisdiction: 'IN-HP'
      }
    });
    expect(ingestRes.status()).toBe(200);
    const ingestBody = await ingestRes.json();
    const docId = ingestBody.document_id;
    expect(docId).toBeDefined();
    expect(ingestBody.chunks).toBeGreaterThan(0);

    // 2. Verify document in indexed documents list
    const listRes = await request.get('http://localhost:8000/api/v1/knowledge/documents', {
      headers: { Authorization: `Bearer ${token}` }
    });
    expect(listRes.status()).toBe(200);
    const listBody = await listRes.json();
    const foundDoc = listBody.items.find((d: any) => d.id === docId);
    expect(foundDoc).toBeDefined();

    // 3. Perform semantic search for the newly indexed clause
    const searchRes = await request.get('http://localhost:8000/api/v1/knowledge/search?q=high-altitude%20mountain%20terrain%20snow%20chains', {
      headers: { Authorization: `Bearer ${token}` }
    });
    expect(searchRes.status()).toBe(200);
    const searchBody = await searchRes.json();
    expect(searchBody.items).toBeDefined();

    // 4. Update document publication status
    const updateRes = await request.put(`http://localhost:8000/api/v1/knowledge/documents/${docId}`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        publication_status: 'published'
      }
    });
    expect(updateRes.status()).toBe(200);
    const updateBody = await updateRes.json();
    expect(updateBody.publication_status).toBe('published');
  });

  test('Cross-Role API Access Control (RBAC Enforcement)', async ({ request }) => {
    // 1. Authenticate as Claimant
    const claimantLogin = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: {
        email: 'riya.claimant@insurance.com',
        password: 'DemoPassword123!'
      }
    });
    expect(claimantLogin.ok()).toBeTruthy();
    const claimantToken = (await claimantLogin.json()).access_token;

    // Claimant tries to access Adjuster Dashboard API -> must be 403
    const adjDashRes = await request.get('http://localhost:8000/api/v1/adjuster/dashboard', {
      headers: { Authorization: `Bearer ${claimantToken}` }
    });
    expect(adjDashRes.status()).toBe(403);

    // Claimant tries to access Adjuster Queue API -> must be 403
    const adjQueueRes = await request.get('http://localhost:8000/api/v1/adjuster/queue', {
      headers: { Authorization: `Bearer ${claimantToken}` }
    });
    expect(adjQueueRes.status()).toBe(403);

    // Claimant tries to access Admin Adjusters API -> must be 403
    const adminAdjRes = await request.get('http://localhost:8000/api/v1/admin/adjusters', {
      headers: { Authorization: `Bearer ${claimantToken}` }
    });
    expect(adminAdjRes.status()).toBe(403);

    // Claimant tries to ingest knowledge -> must be 403
    const knowIngestRes = await request.post('http://localhost:8000/api/v1/knowledge/documents', {
      headers: { Authorization: `Bearer ${claimantToken}` },
      data: {
        source_name: 'unauthorized.txt',
        text: 'Unauthorized knowledge text that should be rejected by RBAC.'
      }
    });
    expect(knowIngestRes.status()).toBe(403);

    // 2. Authenticate as Adjuster
    const adjusterLogin = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: {
        email: 'asha.adjuster@insurance.com',
        password: 'DemoPassword123!'
      }
    });
    expect(adjusterLogin.ok()).toBeTruthy();
    const adjusterToken = (await adjusterLogin.json()).access_token;

    // Adjuster tries to invite another adjuster via Admin API -> must be 403
    const adjInviteRes = await request.post('http://localhost:8000/api/v1/admin/adjusters/invite', {
      headers: { Authorization: `Bearer ${adjusterToken}` },
      data: {
        name: 'Hacker Adjuster',
        email: 'hacker@adjuster.com',
        phone: '9876543210',
        specialization: 'motor'
      }
    });
    expect(adjInviteRes.status()).toBe(403);
  });

  test('IDOR Protection: Claim Isolation Between Claimants', async ({ request }) => {
    // 1. Create a second claimant account via /api/v1/auth/signup
    const secondEmail = `claimant_idor_${Date.now()}@insurance-test.com`;
    const regRes = await request.post('http://localhost:8000/api/v1/auth/signup', {
      data: {
        full_name: 'Isolated Claimant',
        email: secondEmail,
        phone: '+91 97777 88888',
        password: 'DemoPassword123!',
        confirm_password: 'DemoPassword123!'
      }
    });
    expect(regRes.ok()).toBeTruthy();

    const loginRes = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: {
        email: secondEmail,
        password: 'DemoPassword123!'
      }
    });
    expect(loginRes.ok()).toBeTruthy();
    const claimantBToken = (await loginRes.json()).access_token;

    // 2. Claimant B tries to view Claimant A's seeded claim (CLM-DEMO-MOTOR-001)
    const idorClaimRes = await request.get('http://localhost:8000/api/v1/claims/CLM-DEMO-MOTOR-001', {
      headers: { Authorization: `Bearer ${claimantBToken}` }
    });
    // System must reject with 403 Forbidden or 404 Not Found to prevent data leakage
    expect([403, 404]).toContain(idorClaimRes.status());

    // 3. Claimant B tries to interact or submit text turn on Claimant A's claim
    const idorTurnRes = await request.post('http://localhost:8000/api/v1/claims/CLM-DEMO-MOTOR-001/text-turn', {
      headers: { Authorization: `Bearer ${claimantBToken}` },
      data: { text: 'Malicious turn from another user' }
    });
    expect([403, 404]).toContain(idorTurnRes.status());

    // 4. Claimant B tries to upload evidence to Claimant A's claim
    const idorEvidenceRes = await request.post('http://localhost:8000/api/v1/claims/CLM-DEMO-MOTOR-001/evidence', {
      headers: { Authorization: `Bearer ${claimantBToken}` },
      multipart: {
        file: {
          name: 'fake_receipt.txt',
          mimeType: 'text/plain',
          buffer: Buffer.from('unauthorized invoice')
        }
      }
    });
    expect([403, 404]).toContain(idorEvidenceRes.status());
  });

  test('Forgot Password Recovery Lifecycle and Password Reset', async ({ request }) => {
    const recoveryEmail = `recover_${Date.now()}@insurance-test.com`;

    // 1. Create user account
    const regRes = await request.post('http://localhost:8000/api/v1/auth/signup', {
      data: {
        full_name: 'Recovery Test User',
        email: recoveryEmail,
        phone: '+91 99999 11111',
        password: 'InitialPassword123!',
        confirm_password: 'InitialPassword123!'
      }
    });
    expect(regRes.ok()).toBeTruthy();

    // 2. Request forgot password reset
    const forgotRes = await request.post('http://localhost:8000/api/v1/auth/forgot-password', {
      data: { email: recoveryEmail }
    });
    expect(forgotRes.status()).toBe(200);
    const forgotBody = await forgotRes.json();
    expect(forgotBody.message).toBeDefined();

    // 3. Reset password validation: Mismatched passwords rejection
    const resetToken = forgotBody.reset_token;
    if (resetToken) {
      const mismatchRes = await request.post('http://localhost:8000/api/v1/auth/reset-password', {
        data: {
          reset_token: resetToken,
          new_password: 'NewStrongPassword123!',
          confirm_password: 'WrongPassword123!'
        }
      });
      expect(mismatchRes.status()).toBe(400);

      // 4. Successful password reset
      const resetRes = await request.post('http://localhost:8000/api/v1/auth/reset-password', {
        data: {
          reset_token: resetToken,
          new_password: 'NewStrongPassword123!',
          confirm_password: 'NewStrongPassword123!'
        }
      });
      expect(resetRes.status()).toBe(200);

      // 5. Verify old password fails
      const oldLoginRes = await request.post('http://localhost:8000/api/v1/auth/login', {
        data: {
          email: recoveryEmail,
          password: 'InitialPassword123!'
        }
      });
      expect(oldLoginRes.status()).toBe(401);

      // 6. Verify new password succeeds
      const newLoginRes = await request.post('http://localhost:8000/api/v1/auth/login', {
        data: {
          email: recoveryEmail,
          password: 'NewStrongPassword123!'
        }
      });
      expect(newLoginRes.status()).toBe(200);
    }
  });

});
