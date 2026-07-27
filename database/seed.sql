-- Adjusters
INSERT INTO adjusters (id, name, email, specialization, is_active) VALUES
    (gen_random_uuid(), 'Priya Sharma', 'priya.sharma@example.com', 'auto', TRUE),
    (gen_random_uuid(), 'Rahul Mehta', 'rahul.mehta@example.com', 'home', TRUE),
    (gen_random_uuid(), 'Anita Desai', 'anita.desai@example.com', 'complex', TRUE);

-- Policies
INSERT INTO policies (id, policy_number, customer_id, policy_type, coverage_amount, deductible, effective_date, expiry_date, is_active) VALUES
    (gen_random_uuid(), 'XYZ123', gen_random_uuid(), 'auto', 500000, 5000, '2025-01-01', '2026-12-31', TRUE),
    (gen_random_uuid(), 'HOME456', gen_random_uuid(), 'home', 1000000, 10000, '2025-03-01', '2026-02-28', TRUE),
    (gen_random_uuid(), 'AUTO789', gen_random_uuid(), 'auto', 300000, 3000, '2024-06-01', '2025-05-31', FALSE); -- expired, for testing invalid-policy path