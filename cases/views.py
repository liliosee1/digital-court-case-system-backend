from rest_framework import generics

from .models import Case
from .serializers import CaseSerializer


class CaseListCreateAPIView(generics.ListCreateAPIView):
    """List existing cases or create one in the existing cases table."""

    queryset = Case.objects.all().order_by("id")
    serializer_class = CaseSerializer


class CaseDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete one case by its primary key."""

    queryset = Case.objects.all()
    serializer_class = CaseSerializer
