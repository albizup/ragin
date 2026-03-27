"""
Define your ragin models here or in separate files inside this package.

Each model decorated with @resource will auto-generate CRUD endpoints.

Example — add a new model:

    # models/product.py
    from ragin import Field, Model, resource

    @resource(operations=["crud"])
    class Product(Model):
        id: str = Field(primary_key=True)
        name: str
        price: float

Then import it here:
    from models.product import Product
"""
from models.user import User  # noqa: F401

__all__ = ["User"]
