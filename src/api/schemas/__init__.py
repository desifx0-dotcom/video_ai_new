"""
Pydantic-like schemas for request/response validation.
"""
from marshmallow import Schema, fields, validate, validates, validates_schema, ValidationError
from datetime import datetime
from typing import Optional, List, Dict, Any

__all__ = [
    'UserSchema',
    'VideoSchema',
    'AuthSchema',
    'BillingSchema',
    'AdminSchema'
]