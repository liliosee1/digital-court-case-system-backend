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
    class Meta:
        model = Case
        fields = "__all__"


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
