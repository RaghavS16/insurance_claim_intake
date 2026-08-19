-- Canonical seed dataset for development and demonstration
-- Strictly uses the 6 supported insurance types:
-- health, senior_health, home, travel, motor, cyber

-- Adjusters
INSERT INTO adjusters (id, name, email, specialization, is_active) VALUES
    (gen_random_uuid(), 'Priya Sharma',   'priya.motor@insure.co',   'motor',         TRUE),
    (gen_random_uuid(), 'Rohan Mehta',    'rohan.home@insure.co',    'home',          TRUE),
    (gen_random_uuid(), 'Dr. Anita Roy',  'anita.health@insure.co',  'health',        TRUE),
    (gen_random_uuid(), 'Dr. V. Rao',     'rao.senior@insure.co',    'senior_health', TRUE),
    (gen_random_uuid(), 'Vikram Sen',     'vikram.travel@insure.co', 'travel',        TRUE),
    (gen_random_uuid(), 'Neha Kapoor',    'neha.cyber@insure.co',    'cyber',         TRUE)
ON CONFLICT (email) DO NOTHING;

-- Canonical Policies (Initial Unlinked State with Policyholder PII)
INSERT INTO policies (id, policy_number, customer_id, policy_type, coverage_amount, deductible, effective_date, expiry_date, is_active, policyholder_name, policyholder_dob, policyholder_phone_last4, link_attempts) VALUES
    (gen_random_uuid(), 'MOT-5521',  NULL, 'motor',         500000, 5000,  '2024-01-01', '2030-12-31', TRUE, 'John Doe',       '1990-05-15', '1234', 0),
    (gen_random_uuid(), 'XYZ123',    NULL, 'motor',         500000, 10000, '2024-01-01', '2030-12-31', TRUE, 'John Doe',       '1990-05-15', '1234', 0),
    (gen_random_uuid(), 'HOME456',   NULL, 'home',          1000000, 10000, '2025-03-01', '2026-02-28', TRUE, 'Alice Smith',     '1985-08-20', '5678', 0),
    (gen_random_uuid(), 'HLT-7789',  NULL, 'health',        800000, 2000,  '2024-06-01', '2026-05-31', TRUE, 'Robert Johnson', '1978-12-10', '9012', 0),
    (gen_random_uuid(), 'SNR-9912',  NULL, 'senior_health', 600000, 3000,  '2024-01-01', '2027-12-31', TRUE, 'Mary Davis',     '1955-03-25', '3456', 0),
    (gen_random_uuid(), 'TRV-3301',  NULL, 'travel',        200000, 1000,  '2025-01-01', '2025-12-31', TRUE, 'David Wilson',   '1992-11-05', '7890', 0),
    (gen_random_uuid(), 'CYB-8820',  NULL, 'cyber',         1500000, 15000, '2024-01-01', '2026-12-31', TRUE, 'TechCorp LLC',   '2000-01-01', '0000', 0)
ON CONFLICT (policy_number) DO NOTHING;