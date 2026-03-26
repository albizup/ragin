"""Tests for agent/prompt.py — system prompt generation."""
from ragin import Field, Model
from ragin.agent.prompt import generate_system_prompt


class _PromptUser(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str = Field(description="Email address")
    role: str = "member"


def test_prompt_contains_model_name():
    prompt = generate_system_prompt([_PromptUser])
    assert "_PromptUser" in prompt


def test_prompt_contains_table_name():
    prompt = generate_system_prompt([_PromptUser])
    assert "_promptusers" in prompt


def test_prompt_contains_field_names():
    prompt = generate_system_prompt([_PromptUser])
    assert "id" in prompt
    assert "name" in prompt
    assert "email" in prompt
    assert "role" in prompt


def test_prompt_marks_primary_key():
    prompt = generate_system_prompt([_PromptUser])
    assert "(primary key)" in prompt


def test_prompt_includes_field_description():
    prompt = generate_system_prompt([_PromptUser])
    assert "Email address" in prompt


def test_prompt_includes_custom_description():
    prompt = generate_system_prompt([_PromptUser], description="Manages user records.")
    assert "Manages user records." in prompt


def test_prompt_multiple_models():
    class _Item(Model):
        sku: str = Field(primary_key=True)
        title: str

    prompt = generate_system_prompt([_PromptUser, _Item])
    assert "_PromptUser" in prompt
    assert "_Item" in prompt
    assert "sku" in prompt
