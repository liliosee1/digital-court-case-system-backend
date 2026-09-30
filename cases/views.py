from rest_framework import generics

from .models import Case
from .serializers import CaseSerializer


class CaseListAPIView(generics.ListAPIView):
    """Return cases from the existing cases table as JSON."""

    queryset = Case.objects.all().order_by("id")
    serializer_class = CaseSerializer
