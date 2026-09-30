import re

from rest_framework.schemas.openapi import AutoSchema, SchemaGenerator


class CourtAPISchema(AutoSchema):
    """OpenAPI schema support that does not require optional DRF packages."""

    def get_operation_id_base(self, path, method, action):
        model = getattr(getattr(self.view, "queryset", None), "model", None)
        if model is not None:
            name = model.__name__
        else:
            name = self.view.__class__.__name__.removesuffix("APIView").removesuffix("View")
        return f"{name}_{action}"

    def get_path_parameters(self, path, method):
        return [
            {
                "name": name,
                "in": "path",
                "description": "Record identifier.",
                "required": True,
                "schema": {"type": "integer"},
            }
            for name in re.findall(r"\{([^}]+)\}", path)
        ]

    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        authenticators = getattr(self.view, "authentication_classes", ())
        if any(authenticator.__name__ == "BearerTokenAuthentication" for authenticator in authenticators):
            operation["security"] = [{"BearerAuth": []}]
        return operation


class CourtAPISchemaGenerator(SchemaGenerator):
    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request=request, public=public)
        if schema is not None:
            schema.setdefault("components", {}).setdefault("securitySchemes", {})[
                "BearerAuth"
            ] = {"type": "http", "scheme": "bearer", "bearerFormat": "signed token"}
        return schema
