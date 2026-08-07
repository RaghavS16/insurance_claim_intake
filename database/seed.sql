-- FIX 4: Aligned with schema.sql seed data and conftest.py test seed.
-- Previously: wrong email domain (example.com vs insure.co), wrong adjuster name
-- (Rahul vs Rohan), missing 'business' adjuster, missing AUTO789 expired policy.

-- Adjusters
INSERT INTO adjusters (id, name, email, specialization, is_active) VALUES
    (gen_random_uuid(), 'Priya Sharma',   'priya@insure.co',    'auto',     TRUE),
    (gen_random_uuid(), 'Rohan Mehta',    'rohan@insure.co',    'home',     TRUE),
    (gen_random_uuid(), 'Anjali Gupta',   'anjali@insure.co',   'business', TRUE),
    (gen_random_uuid(), 'Complex Review', 'complex@insure.co',  'complex',  TRUE)
ON CONFLICT (email) DO NOTHING;

-- Policies
INSERT INTO policies (id, policy_number, customer_id, policy_type, coverage_amount, deductible, effective_date, expiry_date, is_active) VALUES
    (gen_random_uuid(), 'XYZ123',  gen_random_uuid(), 'auto', 500000, 10000, '2024-01-01', '2030-12-31', TRUE),
    (gen_random_uuid(), 'HOME456', gen_random_uuid(), 'home', 1000000, 10000, '2025-03-01', '2026-02-28', TRUE),
    (gen_random_uuid(), 'AUTO789', gen_random_uuid(), 'auto', 300000, 5000, '2020-01-01', '2022-12-31', FALSE) -- expired, for testing invalid-policy path
ON CONFLICT (policy_number) DO NOTHING;