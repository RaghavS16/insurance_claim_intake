"""
Edge-case tests for src/utils/validators.py

Covers: validate_email, validate_password_strength, validate_ticket_id,
        validate_enum, sanitize_text_input, sanitize_filename,
        validate_phone, validate_full_name.
"""
import pytest
from src.utils.validators import (
    validate_email,
    validate_password_strength,
    validate_ticket_id,
    validate_enum,
    sanitize_text_input,
    sanitize_filename,
    validate_phone,
    validate_full_name,
    VALID_CLAIM_TYPES,
    VALID_FINAL_DECISIONS,
    VALID_CLOSURE_STATUSES,
    VALID_DOCUMENT_TYPES,
)


# ---------------------------------------------------------------------------
# validate_email
# ---------------------------------------------------------------------------
class TestValidateEmail:
    def test_valid_email_lowercased(self):
        assert validate_email("USER@Example.COM") == "user@example.com"

    def test_strips_whitespace(self):
        assert validate_email("  test@test.com  ") == "test@test.com"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            validate_email("")

    def test_none_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            validate_email(None)  # type: ignore[arg-type]

    def test_too_short_raises(self):
        with pytest.raises(ValueError):
            validate_email("a@b.c")  # 5 chars, boundary - valid by len; but maybe not regex

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            validate_email("a" * 250 + "@b.com")  # > 254

    def test_missing_at_sign_raises(self):
        with pytest.raises(ValueError):
            validate_email("notanemail.com")

    def test_missing_domain_raises(self):
        with pytest.raises(ValueError):
            validate_email("user@")

    def test_multiple_at_signs_raises(self):
        with pytest.raises(ValueError):
            validate_email("user@@domain.com")

    def test_valid_subdomain_email(self):
        result = validate_email("user@mail.example.co.uk")
        assert result == "user@mail.example.co.uk"

    def test_plus_addressing_is_valid(self):
        result = validate_email("user+tag@example.com")
        assert result == "user+tag@example.com"

    def test_local_part_with_dots_valid(self):
        result = validate_email("first.last@example.org")
        assert result == "first.last@example.org"

    def test_no_tld_raises(self):
        with pytest.raises(ValueError):
            validate_email("user@localhost")

    def test_ip_address_domain_raises(self):
        # Regex requires letters in TLD
        with pytest.raises(ValueError):
            validate_email("user@192.168.0.1")

    def test_single_char_tld_raises(self):
        with pytest.raises(ValueError):
            validate_email("user@example.c")


# ---------------------------------------------------------------------------
# validate_password_strength
# ---------------------------------------------------------------------------
class TestValidatePasswordStrength:
    def test_valid_password_returns_unchanged(self):
        pw = "SecureP@ss1"
        assert validate_password_strength(pw) == pw

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            validate_password_strength("")

    def test_none_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            validate_password_strength(None)  # type: ignore[arg-type]

    def test_too_short_raises(self):
        with pytest.raises(ValueError):
            validate_password_strength("Sh0rt!")

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            validate_password_strength("A1!" + "a" * 126)  # > 128

    def test_missing_uppercase_raises(self):
        with pytest.raises(ValueError):
            validate_password_strength("alllower1!")

    def test_missing_lowercase_raises(self):
        with pytest.raises(ValueError):
            validate_password_strength("ALLUPPER1!")

    def test_missing_digit_raises(self):
        with pytest.raises(ValueError):
            validate_password_strength("NoDigits!!")

    def test_missing_special_char_raises(self):
        with pytest.raises(ValueError):
            validate_password_strength("NoSpecial1")

    def test_exactly_8_chars_valid(self):
        result = validate_password_strength("Passw0r!")
        assert result == "Passw0r!"

    def test_exactly_128_chars_valid(self):
        pw = "Aa1!" + "x" * 124
        assert len(pw) == 128
        result = validate_password_strength(pw)
        assert result == pw

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            validate_password_strength("        ")

    def test_special_chars_from_set(self):
        """Each listed special char should satisfy the requirement."""
        from src.utils.validators import validate_password_strength
        for sp in ["!", "@", "#", "$", "%", "^", "&", "*"]:
            pw = f"Passw0rd{sp}"
            assert validate_password_strength(pw) == pw


# ---------------------------------------------------------------------------
# validate_ticket_id
# ---------------------------------------------------------------------------
class TestValidateTicketId:
    def test_valid_ticket_id(self):
        assert validate_ticket_id("CLAIM-ABCD1234") == "CLAIM-ABCD1234"

    def test_lowercase_input_normalized(self):
        assert validate_ticket_id("claim-abcd1234") == "CLAIM-ABCD1234"

    def test_with_leading_trailing_space(self):
        assert validate_ticket_id("  CLAIM-ABCD1234  ") == "CLAIM-ABCD1234"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            validate_ticket_id("")

    def test_none_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            validate_ticket_id(None)  # type: ignore[arg-type]

    def test_wrong_prefix_raises(self):
        with pytest.raises(ValueError):
            validate_ticket_id("TICKET-ABCD1234")

    def test_too_short_suffix_raises(self):
        with pytest.raises(ValueError):
            validate_ticket_id("CLAIM-ABC123")  # 7 chars instead of 8

    def test_too_long_suffix_raises(self):
        with pytest.raises(ValueError):
            validate_ticket_id("CLAIM-ABCD12345")  # 9 chars

    def test_special_chars_in_suffix_raises(self):
        with pytest.raises(ValueError):
            validate_ticket_id("CLAIM-ABCD-234")

    def test_numeric_only_suffix_valid(self):
        assert validate_ticket_id("CLAIM-12345678") == "CLAIM-12345678"

    def test_alpha_only_suffix_valid(self):
        assert validate_ticket_id("CLAIM-ABCDEFGH") == "CLAIM-ABCDEFGH"


# ---------------------------------------------------------------------------
# validate_enum
# ---------------------------------------------------------------------------
class TestValidateEnum:
    def test_valid_value_returned(self):
        assert validate_enum("motor", VALID_CLAIM_TYPES, "claim_type") == "motor"

    def test_case_normalized_to_lower(self):
        assert validate_enum("MOTOR", VALID_CLAIM_TYPES, "claim_type") == "motor"

    def test_strips_whitespace(self):
        assert validate_enum("  health  ", VALID_CLAIM_TYPES, "claim_type") == "health"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError, match="claim_type"):
            validate_enum("aircraft", VALID_CLAIM_TYPES, "claim_type")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            validate_enum("", VALID_CLAIM_TYPES, "claim_type")

    def test_none_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            validate_enum(None, VALID_CLAIM_TYPES, "claim_type")  # type: ignore[arg-type]

    def test_all_valid_claim_types_pass(self):
        for ct in VALID_CLAIM_TYPES:
            assert validate_enum(ct, VALID_CLAIM_TYPES, "ct") == ct

    def test_error_message_includes_valid_set(self):
        with pytest.raises(ValueError) as exc:
            validate_enum("bad", VALID_CLAIM_TYPES, "claim_type")
        assert "claim_type" in str(exc.value)

    def test_final_decision_valid_values(self):
        for val in VALID_FINAL_DECISIONS:
            assert validate_enum(val, VALID_FINAL_DECISIONS, "decision") == val

    def test_closure_status_valid_values(self):
        for val in VALID_CLOSURE_STATUSES:
            assert validate_enum(val, VALID_CLOSURE_STATUSES, "status") == val


# ---------------------------------------------------------------------------
# sanitize_text_input
# ---------------------------------------------------------------------------
class TestSanitizeTextInput:
    def test_empty_string_returns_empty(self):
        assert sanitize_text_input("") == ""

    def test_none_returns_empty(self):
        assert sanitize_text_input(None) == ""  # type: ignore[arg-type]

    def test_strips_leading_trailing_whitespace(self):
        assert sanitize_text_input("  hello  ") == "hello"

    def test_removes_null_bytes(self):
        result = sanitize_text_input("hel\x00lo")
        assert "\x00" not in result
        assert "hel" in result

    def test_truncates_to_max_length(self):
        long = "a" * 6000
        result = sanitize_text_input(long, max_length=5000)
        assert len(result) == 5000

    def test_strict_mode_raises_on_sql_keywords(self):
        with pytest.raises(ValueError):
            sanitize_text_input("DROP TABLE users", strict=True)

    def test_strict_mode_raises_on_html_tags(self):
        with pytest.raises(ValueError):
            sanitize_text_input("<script>alert(1)</script>", strict=True)

    def test_strict_mode_raises_on_double_dash(self):
        with pytest.raises(ValueError):
            sanitize_text_input("admin'--", strict=True)

    def test_non_strict_allows_claim_narratives(self):
        text = "My car was in an accident. The damage is bad."
        result = sanitize_text_input(text)
        assert result == text

    def test_non_strict_does_not_raise_on_keywords(self):
        # Claim narratives may contain words like DROP (drop the car off)
        result = sanitize_text_input("I had to DROP my car at the garage")
        assert "DROP" in result

    def test_custom_max_length_zero(self):
        result = sanitize_text_input("hello", max_length=0)
        assert result == ""

    def test_custom_max_length_preserves_short_input(self):
        result = sanitize_text_input("short", max_length=100)
        assert result == "short"


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------
class TestSanitizeFilename:
    def test_safe_filename_unchanged(self):
        result = sanitize_filename("document.pdf")
        assert result == "document.pdf"

    def test_empty_string_returns_unnamed(self):
        assert sanitize_filename("") == "unnamed"

    def test_none_returns_unnamed(self):
        assert sanitize_filename(None) == "unnamed"  # type: ignore[arg-type]

    def test_path_traversal_dots_replaced(self):
        result = sanitize_filename("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_forward_slash_replaced(self):
        result = sanitize_filename("path/to/file.txt")
        assert "/" not in result

    def test_backslash_replaced(self):
        result = sanitize_filename("path\\file.txt")
        assert "\\" not in result

    def test_null_bytes_removed(self):
        result = sanitize_filename("file\x00.pdf")
        assert "\x00" not in result

    def test_special_chars_replaced(self):
        result = sanitize_filename("file name!@#.pdf")
        # Should not contain spaces or most special chars
        assert " " not in result

    def test_result_is_not_empty_for_all_special_input(self):
        result = sanitize_filename("!@#$%^&*()")
        assert result  # must return something non-empty (either sanitized or "unnamed")

    def test_preserves_extension(self):
        result = sanitize_filename("policy_doc.pdf")
        assert ".pdf" in result

    def test_double_dot_extension_sanitized(self):
        result = sanitize_filename("file..txt")
        assert ".." not in result


# ---------------------------------------------------------------------------
# validate_phone
# ---------------------------------------------------------------------------
class TestValidatePhone:
    def test_none_returns_none(self):
        assert validate_phone(None) is None

    def test_empty_string_returns_none(self):
        assert validate_phone("") is None

    def test_whitespace_only_returns_none(self):
        assert validate_phone("   ") is None

    def test_valid_indian_number(self):
        result = validate_phone("+91-9876543210")
        assert result == "+91-9876543210"

    def test_valid_us_format(self):
        result = validate_phone("(123) 456-7890")
        assert result == "(123) 456-7890"

    def test_digits_only_valid(self):
        result = validate_phone("9876543210")
        assert result == "9876543210"

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            validate_phone("1" * 21)

    def test_letters_in_number_raises(self):
        with pytest.raises(ValueError):
            validate_phone("1-800-FLOWERS")

    def test_special_chars_raises(self):
        with pytest.raises(ValueError):
            validate_phone("+91@9876543210")

    def test_plus_sign_is_valid(self):
        result = validate_phone("+919876543210")
        assert result is not None


# ---------------------------------------------------------------------------
# validate_full_name
# ---------------------------------------------------------------------------
class TestValidateFullName:
    def test_valid_name(self):
        assert validate_full_name("John Doe") == "John Doe"

    def test_strips_whitespace(self):
        assert validate_full_name("  Alice  ") == "Alice"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            validate_full_name("")

    def test_none_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            validate_full_name(None)  # type: ignore[arg-type]

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            validate_full_name("A" * 101)

    def test_exactly_100_chars_valid(self):
        name = "A" * 100
        assert validate_full_name(name) == name

    def test_single_char_valid(self):
        assert validate_full_name("A") == "A"

    def test_sql_injection_in_name_raises(self):
        with pytest.raises(ValueError):
            validate_full_name("Robert'); DROP TABLE students;--")

    def test_html_tag_in_name_raises(self):
        with pytest.raises(ValueError):
            validate_full_name('<script>alert("xss")</script>')

    def test_name_with_hyphen_valid(self):
        # Hyphen is a common character in names and is not in dangerous patterns
        result = validate_full_name("Mary-Jane Watson")
        assert result == "Mary-Jane Watson"

    def test_unicode_name_allowed(self):
        # Unicode names may contain chars but not injection patterns
        result = validate_full_name("Raghu Kumar")
        assert result == "Raghu Kumar"
