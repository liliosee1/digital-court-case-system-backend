from rest_framework import serializers

from .models import Case, CaseHistory, CaseParty, Courtroom, Hearing, Party, Role, User


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    # Password hashes must never be included in an API response.
    class Meta:
        model = User
        exclude = ("password_hash",)


class CaseSerializer(serializers.ModelSerializer):
    assigned_judge = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        allow_null=True,
        required=False,
    )
    created_by = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    class Meta:
        model = Case
        fields = (
            "id",
            "case_number",
            "case_type",
            "title",
            "description",
            "filing_date",
            "status",
            "assigned_judge",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class PartySerializer(serializers.ModelSerializer):
    class Meta:
        model = Party
        fields = "__all__"


class CasePartySerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseParty
        fields = "__all__"


class CourtroomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Courtroom
        fields = "__all__"


class HearingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hearing
        fields = "__all__"


class CaseHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseHistory
        fields = "__all__"
