"""
Tests for code autocomplete endpoint.

This module tests the autocomplete functionality including:
    - Language-specific suggestions
    - Context-aware completions
    - Different programming languages
    - Edge cases and error handling
"""

import pytest
from httpx import AsyncClient


# ============================================================================
# PYTHON AUTOCOMPLETE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_autocomplete_def_keyword(client: AsyncClient):
    """
    Test autocomplete for Python 'def' keyword.
    
    Verifies that function definition suggestion is returned.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "def ",
            "cursor_position": 4,
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    assert "confidence" in data
    assert "function_name" in data["suggestion"].lower() or "self" in data["suggestion"]
    assert 0.0 <= data["confidence"] <= 1.0
    assert data["confidence"] >= 0.8  # Should be high confidence


@pytest.mark.asyncio
async def test_autocomplete_class_keyword(client: AsyncClient):
    """
    Test autocomplete for Python 'class' keyword.
    
    Verifies that class definition suggestion is returned.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "class ",
            "cursor_position": 6,
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    assert "ClassName" in data["suggestion"] or "class" in data["suggestion"].lower()
    assert data["confidence"] >= 0.8


@pytest.mark.asyncio
async def test_autocomplete_import_keyword(client: AsyncClient):
    """
    Test autocomplete for Python 'import' keyword.
    
    Verifies that import suggestions are returned.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "import ",
            "cursor_position": 7,
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    # Should suggest common imports
    assert any(lib in data["suggestion"] for lib in ["os", "sys", "json"])
    assert data["confidence"] >= 0.75


@pytest.mark.asyncio
async def test_autocomplete_for_loop(client: AsyncClient):
    """
    Test autocomplete for Python 'for' loop.
    
    Verifies that loop structure suggestion is returned.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "for ",
            "cursor_position": 4,
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    assert "in" in data["suggestion"] or "range" in data["suggestion"]
    assert data["confidence"] >= 0.7


@pytest.mark.asyncio
async def test_autocomplete_if_statement(client: AsyncClient):
    """
    Test autocomplete for Python 'if' statement.
    
    Verifies that conditional structure suggestion is returned.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "if ",
            "cursor_position": 3,
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    assert ":" in data["suggestion"] or "condition" in data["suggestion"]


@pytest.mark.asyncio
async def test_autocomplete_print_function(client: AsyncClient):
    """
    Test autocomplete for Python 'print' function.
    
    Verifies context-aware suggestions within function calls.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "print(",
            "cursor_position": 6,
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    # Should suggest string literal or Hello World
    assert data["confidence"] >= 0.5


# ============================================================================
# JAVASCRIPT AUTOCOMPLETE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_autocomplete_javascript_function(client: AsyncClient):
    """
    Test autocomplete for JavaScript 'function' keyword.
    
    Verifies language-specific suggestions for JavaScript.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "function ",
            "cursor_position": 9,
            "language": "javascript"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    assert "{" in data["suggestion"] or "Function" in data["suggestion"]
    assert data["confidence"] >= 0.8


@pytest.mark.asyncio
async def test_autocomplete_javascript_const(client: AsyncClient):
    """
    Test autocomplete for JavaScript 'const' keyword.
    
    Verifies variable declaration suggestions.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "const ",
            "cursor_position": 6,
            "language": "javascript"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    assert "=" in data["suggestion"] or "variable" in data["suggestion"].lower()


@pytest.mark.asyncio
async def test_autocomplete_javascript_console(client: AsyncClient):
    """
    Test autocomplete for JavaScript 'console.log'.
    
    Verifies context-aware suggestions for console methods.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "console.log(",
            "cursor_position": 12,
            "language": "javascript"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data


# ============================================================================
# TYPESCRIPT AUTOCOMPLETE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_autocomplete_typescript_interface(client: AsyncClient):
    """
    Test autocomplete for TypeScript 'interface' keyword.
    
    Verifies TypeScript-specific suggestions.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "interface ",
            "cursor_position": 10,
            "language": "typescript"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    # TypeScript suggestions might include interface names or structures


@pytest.mark.asyncio
async def test_autocomplete_typescript_type(client: AsyncClient):
    """
    Test autocomplete for TypeScript 'type' keyword.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "type ",
            "cursor_position": 5,
            "language": "typescript"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    assert data["confidence"] >= 0.5


# ============================================================================
# JAVA AUTOCOMPLETE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_autocomplete_java_class(client: AsyncClient):
    """
    Test autocomplete for Java 'class' keyword.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "class ",
            "cursor_position": 6,
            "language": "java"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    assert "{" in data["suggestion"] or "Class" in data["suggestion"]


@pytest.mark.asyncio
async def test_autocomplete_java_public(client: AsyncClient):
    """
    Test autocomplete for Java 'public' keyword.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "public ",
            "cursor_position": 7,
            "language": "java"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    assert "class" in data["suggestion"].lower() or "{" in data["suggestion"]


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================

@pytest.mark.asyncio
async def test_autocomplete_empty_code(client: AsyncClient):
    """
    Test autocomplete with empty code.
    
    Verifies that default suggestions are returned.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "",
            "cursor_position": 0,
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    assert "confidence" in data
    # Default suggestion should have lower confidence
    assert data["confidence"] <= 0.6


@pytest.mark.asyncio
async def test_autocomplete_cursor_at_zero(client: AsyncClient):
    """
    Test autocomplete with cursor at position 0.
    
    Verifies handling of cursor at the beginning.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "print('hello')",
            "cursor_position": 0,
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data


@pytest.mark.asyncio
async def test_autocomplete_cursor_beyond_code(client: AsyncClient):
    """
    Test autocomplete with cursor position beyond code length.
    
    Verifies that the full code is used for context.
    """
    code = "def test()"
    
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": code,
            "cursor_position": len(code) + 100,  # Way beyond
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data


@pytest.mark.asyncio
async def test_autocomplete_different_languages(client: AsyncClient):
    """
    Test autocomplete across different programming languages.
    
    Verifies that language-specific suggestions are provided.
    """
    languages = ["python", "javascript", "typescript", "java"]
    
    for language in languages:
        response = await client.post(
            "/api/v1/autocomplete",
            json={
                "code": "test",
                "cursor_position": 4,
                "language": language
            }
        )
        
        assert response.status_code == 200, f"Failed for language: {language}"
        data = response.json()
        
        assert "suggestion" in data
        assert "confidence" in data
        assert 0.0 <= data["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_autocomplete_long_code(client: AsyncClient):
    """
    Test autocomplete with long code snippet.
    
    Verifies handling of large code contexts.
    """
    long_code = """
def function1():
    pass

def function2():
    pass

def function3():
    pass

# Current cursor position
for 
"""
    
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": long_code,
            "cursor_position": len(long_code),
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "suggestion" in data
    # Should suggest loop completion
    assert "in" in data["suggestion"] or "range" in data["suggestion"]


@pytest.mark.asyncio
async def test_autocomplete_invalid_language(client: AsyncClient):
    """
    Test autocomplete with invalid language.
    
    Verifies error handling for unsupported languages.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "test",
            "cursor_position": 4,
            "language": "cobol"  # Not in our supported list
        }
    )
    
    # Should return 422 validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_autocomplete_negative_cursor_position(client: AsyncClient):
    """
    Test autocomplete with negative cursor position.
    
    Verifies validation of cursor position.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "test",
            "cursor_position": -1,
            "language": "python"
        }
    )
    
    # Should return 422 validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_autocomplete_missing_required_fields(client: AsyncClient):
    """
    Test autocomplete with missing required fields.
    
    Verifies proper validation error handling.
    """
    # Missing 'code' field
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "cursor_position": 4,
            "language": "python"
        }
    )
    
    assert response.status_code == 422
    
    # Missing 'cursor_position' field
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "test",
            "language": "python"
        }
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_autocomplete_response_structure(client: AsyncClient):
    """
    Test that autocomplete response has correct structure.
    
    Verifies response schema compliance.
    """
    response = await client.post(
        "/api/v1/autocomplete",
        json={
            "code": "def ",
            "cursor_position": 4,
            "language": "python"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify required fields
    assert "suggestion" in data
    assert "confidence" in data
    
    # Verify types
    assert isinstance(data["suggestion"], str)
    assert isinstance(data["confidence"], (int, float))
    
    # Verify confidence range
    assert 0.0 <= data["confidence"] <= 1.0

