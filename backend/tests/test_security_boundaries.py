from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from src.utils.authorization import enforce_claim_ownership
from src.utils.mfa import new_totp_secret, encrypt_secret, decrypt_secret, verify_totp, new_recovery_codes, hash_recovery_code, verify_recovery_hash

def test_cross_tenant_claim_is_denied():
    claim=SimpleNamespace(id="c1", tenant_id="tenant-a", claimant_id="u1", customer_id="u1")
    user=SimpleNamespace(id="u1", tenant_id="tenant-b", role="CLAIMANT")
    with pytest.raises(HTTPException) as exc:
        enforce_claim_ownership(claim,user)
    assert exc.value.status_code == 403

def test_same_tenant_claim_owner_is_allowed():
    claim=SimpleNamespace(id="c1", tenant_id="tenant-a", claimant_id="u1", customer_id="u1")
    user=SimpleNamespace(id="u1", tenant_id="tenant-a", role="CLAIMANT")
    enforce_claim_ownership(claim,user)

def test_totp_secret_is_encrypted_and_verifiable():
    secret=new_totp_secret()
    ciphertext=encrypt_secret(secret)
    assert ciphertext != secret
    assert decrypt_secret(ciphertext) == secret
    assert verify_totp(secret, __import__("pyotp").TOTP(secret).now())

def test_recovery_codes_are_one_way_hashes():
    code=new_recovery_codes(1)[0]
    digest=hash_recovery_code(code)
    assert digest != code
    assert verify_recovery_hash(code,digest)
    assert not verify_recovery_hash("WRONG",digest)
